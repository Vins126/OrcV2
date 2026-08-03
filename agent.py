"""Agente ReAct: il nucleo esecutivo del sistema ORC.

Implementa l'unità atomica dell'architettura — un modello linguistico chiuso in
un ciclo che gli permette di usare strumenti e di osservarne i risultati, fino a
completare il compito assegnato.

Il ciclo ReAct (Reason + Act):
    1. il modello riceve la conversazione e decide;
    2. se chiede uno o più tool, questi vengono eseguiti;
    3. i risultati rientrano nella conversazione come *osservazioni*;
    4. si torna al punto 1, con più informazione di prima.
    Il ciclo termina quando il modello risponde a parole senza chiedere tool.

Nota di design (tesi):
    Questo modulo è il **milestone M1** e svolge due ruoli nel lavoro complessivo:

    - è la **baseline mono-modello**, cioè il termine di paragone che la tesi
      deve battere: un solo modello fisso, chiamato per ogni passo, senza alcuna
      scelta di costo;
    - è il **worker** dello swarm di M2: nell'architettura futura ogni agente
      sarà un'istanza di questa classe con un modello diverso, assegnato dal
      router. Per questo il modello non è cablato ma iniettato nel costruttore:
      quel singolo parametro è il punto in cui il cost-routing si innesterà.

    Un secondo principio attraversa tutto il file — gli **errori non
    interrompono il ciclo, diventano osservazioni**. Un JSON malformato, un tool
    inesistente, un comando fallito: tutto viene catturato e restituito al
    modello come testo che lui può leggere. È la resilienza per auto-correzione,
    e riproduce alla scala più piccola lo stesso schema "valuta e reagisci" che
    in M2 governerà l'escalation di modello.

Limite noto:
    Il campo `usage` della risposta API (numero di token consumati) viene
    attualmente scartato in `_chiama_llm`. È l'informazione da cui si ricava il
    costo di ogni chiamata, e quindi il primo elemento da introdurre per la
    contabilità dei costi prevista da M2.
"""

import json
import logging
import time

from openai import OpenAI

import config
from alerts import Alerts
from loop_detector import RilevatoreLoop
from tools import ALL_TOOLS

# Un logger per modulo. Il nome segue la gerarchia dei moduli (__name__).
log = logging.getLogger(__name__)

#: Istruzioni di sistema anteposte a ogni conversazione. Dichiarano al modello
#: quali capacità ha, che gli errori sono recuperabili in autonomia e — punto
#: essenziale — qual è la condizione di terminazione: rispondere senza chiamare
#: tool. Senza quest'ultima indicazione il ciclo non avrebbe una fine naturale.
SYSTEM_PROMPT = (
    "Sei un agente. Hai il tool bash per eseguire comandi shell. Usalo per "
    "completare il compito. Se ci sono errori analizza i tuoi tool per capire "
    "se puoi risolverli in autonomia. Quando hai finito, rispondi a parole "
    "SENZA chiamare tool. "
)


class Agent:
    """Modello linguistico in un ciclo ReAct, dotato di strumenti.

    Le dipendenze (client, modello, tool) sono iniettate dall'esterno anziché
    costruite internamente. Ne derivano due proprietà: la classe è testabile con
    un client finto, senza chiamate di rete né costi; ed è riutilizzabile con
    modelli e set di strumenti diversi, che è il presupposto dello swarm di M2.

    Attributes:
        client: client compatibile con l'API OpenAI, già configurato.
        model: identificatore del modello da interrogare.
        tools: strumenti messi a disposizione del modello.
        tool_schemas: descrizioni dei tool nel formato atteso dall'API.
        tool_registry: mappa nome→tool, per ritrovare lo strumento richiesto
            dal modello in tempo costante.
    """

    def __init__(self, client, model, tools):
        """Registra le dipendenze e precalcola le strutture di lookup.

        Schemi e registro sono costruiti una sola volta qui, non a ogni
        iterazione: sono invarianti per tutta la vita dell'agente.

        Args:
            client: client dell'API (o un suo sostituto nei test).
            model: nome del modello da usare per ogni chiamata.
            tools: lista di istanze di `tools.base.Tool`.
        """
        self.client = client
        self.model = model
        self.tools = tools
        self.tool_schemas = [t.schema for t in tools]
        self.tool_registry = {t.name: t for t in tools}

    def run(self, task, max_iterations=config.MAX_ITERAZIONI):
        """Esegue un task fino al completamento o all'esaurimento delle iterazioni.

        Il tetto di iterazioni è una garanzia di terminazione: un agente che non
        converge deve fermarsi comunque, perché ogni iterazione ha un costo in
        token che cresce insieme alla conversazione.

        Il rilevatore di loop viene creato qui, per ogni task: il suo stato
        (quante volte è stata ripetuta l'ultima azione) è specifico
        dell'esecuzione corrente e non deve sopravvivere al task successivo.

        Args:
            task: descrizione in linguaggio naturale del compito da svolgere.
            max_iterations: numero massimo di passi ReAct concessi.
        """
        messages = self._messaggi_iniziali(task)
        rilevatore = RilevatoreLoop(config.ALERT_THRESHOLD, config.LOOP_THRESHOLD)
        log.info("Task avviato: %s", task)

        for iterazione in range(1, max_iterations + 1):
            log.debug("--- iterazione %d/%d ---", iterazione, max_iterations)
            if not self._esegui_iterazione(messages, rilevatore, iterazione):
                return

        log.error("Raggiunto il limite di %d iterazioni", max_iterations)
        print(f"AGENTE: limite di {max_iterations} iterazioni raggiunto, mi fermo.")

    def _esegui_iterazione(self, messages, rilevatore, iterazione) -> bool:
        """Esegue un passo ReAct. Ritorna True se il task deve continuare, False se è concluso.

        Concentra le tre condizioni che possono chiudere un task — servizio
        irraggiungibile, compito completato, loop persistente — e altrimenti
        esegue i tool richiesti.

        L'ordine delle operazioni non è arbitrario:
            - il controllo del loop precede l'esecuzione dei tool, per non pagare
              l'ennesima ripetizione di un'azione già riconosciuta come sterile;
            - l'eventuale avviso viene accodato *dopo* i risultati dei tool, così
              che sia l'ultimo messaggio letto dal modello e pesi sulla decisione
              immediatamente successiva.

        Args:
            messages: conversazione corrente; viene **modificata sul posto**, e
                cresce a ogni iterazione con la risposta del modello e le
                osservazioni prodotte dai tool.
            rilevatore: rilevatore di loop associato a questo task.
            iterazione: numero del passo corrente, usato solo per il logging.

        Returns:
            True se il ciclo deve proseguire, False se il task è terminato (per
            completamento, per servizio non raggiungibile o per loop).
        """
        try:
            msg = self._chiama_llm(messages)
        except RuntimeError as e:
            log.error("Interrompo il task: %s", e)
            print("AGENTE: Servizio LLM non raggiungibile. Riprova più tardi.")
            return False

        # L'AI non chiede tool -> ha finito
        if not msg.tool_calls:
            log.info("Task completato in %d iterazioni", iterazione)
            print("AGENTE:", msg.content)
            return False

        # Rilevo loop per evitare sprechi
        verdetto = rilevatore.in_loop_verdict(msg.tool_calls)
        if verdetto == Alerts.FERMA:
            log.error("Loop persistente (%d ripetizioni): interrompo", rilevatore.ripetizioni)
            print("AGENTE: Loop persistente, non sono riuscito a risolvere il problema.")
            return False

        # L'AI chiede tool -> li eseguo
        messages.append(msg)
        self._esegui_tool_calls(messages, msg)

        # Potenziale loop -> avviso il modello e gli do una chance
        if verdetto == Alerts.AVVISA:
            log.warning("Possibile loop (%d ripetizioni): avviso il modello", rilevatore.ripetizioni)
            messages.append({"role": "user", "content": verdetto.avviso})

        return True

    def _messaggi_iniziali(self, task):
        """Costruisce la conversazione di partenza.

        Args:
            task: compito assegnato dall'utente.

        Returns:
            Lista con il messaggio di sistema seguito dal task dell'utente.
        """
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]

    def _chiama_llm(self, messages):
        """Interroga il modello, riprovando con backoff esponenziale sui fallimenti.

        L'intera conversazione viene rispedita a ogni chiamata: il modello non ha
        memoria tra una richiesta e l'altra, e l'illusione di continuità è
        prodotta interamente dal contenuto di `messages`. Ne segue che il costo di
        un'iterazione cresce con la lunghezza della conversazione, e che il costo
        totale di un task non è lineare nel numero di passi.

        Il ritardo tra i tentativi è `RETRY_DELAY ** tentativo`, cioè 1s, 2s, 4s:
        un servizio momentaneamente sovraccarico ha il tempo di riprendersi,
        senza che l'attesa complessiva diventi eccessiva.

        Args:
            messages: conversazione completa da inviare al modello.

        Returns:
            Il messaggio prodotto dal modello, con `content` e/o `tool_calls`.

        Raises:
            RuntimeError: se tutti i tentativi falliscono. È un'eccezione distinta
                e volutamente generica: al chiamante interessa solo che il
                servizio non sia raggiungibile, non quale errore di rete sia
                occorso.

        Limite noto:
            Si conserva solo `risposta.choices[0].message` e si scarta
            `risposta.usage`, che contiene il conteggio dei token di input e di
            output. È l'informazione necessaria a calcolare il costo di ogni
            chiamata: catturarla è il primo passo verso la contabilità dei costi.
        """
        for tentativo in range(config.RETRY_MAX):
            try:
                risposta = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tool_schemas,
                )
                msg = risposta.choices[0].message
                self._log_risposta(msg)
                return msg

            except Exception as e:
                attesa = config.RETRY_DELAY ** tentativo
                log.warning("Tentativo %d/%d fallito: %s. Riprovo tra %d secondi",
                            tentativo + 1, config.RETRY_MAX, e, attesa)
                if tentativo < config.RETRY_MAX - 1:
                    time.sleep(attesa)

        log.error("Impossibile connettersi al modello dopo %d tentativi", config.RETRY_MAX)
        raise RuntimeError("LLM irraggiungibile")

    def _log_risposta(self, msg):
        """Registra a livello DEBUG cosa ha deciso il modello.

        Distingue i due esiti possibili di un'iterazione — azione o conclusione —
        perché è la traccia che permette di ricostruire a posteriori il percorso
        di ragionamento seguito dall'agente.

        Args:
            msg: messaggio restituito dal modello.
        """
        if msg.tool_calls:
            log.debug("LLM richiede %d tool: %s", len(msg.tool_calls),
                      [tc.function.name for tc in msg.tool_calls])
        else:
            log.debug("LLM risponde a parole: %s", (msg.content or "")[:200])

    def _esegui_tool_calls(self, messages, msg):
        """Esegue tutte le tool call richieste e ne accoda i risultati.

        Ogni risultato viene accodato come messaggio con ruolo `tool` e con il
        `tool_call_id` corrispondente: è l'identificatore che permette al modello
        di associare ciascuna osservazione alla richiesta che l'ha generata,
        indispensabile quando in una sola iterazione vengono richiesti più tool.

        Args:
            messages: conversazione, modificata sul posto con le osservazioni.
            msg: messaggio del modello contenente le tool call da eseguire.
        """
        for tool_call in msg.tool_calls:
            risultato = self._esegui_singolo_tool(tool_call)
            log.debug("tool %s(%s) -> %s",
                      tool_call.function.name, tool_call.function.arguments, risultato)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(risultato),
            })

    def _esegui_singolo_tool(self, tool_call):
        """Esegue una singola tool call, convertendo ogni fallimento in un esito leggibile.

        Sono previsti tre modi di fallire, e nessuno interrompe il ciclo:
            1. gli argomenti non sono JSON valido (il modello ha prodotto testo
               malformato);
            2. il tool richiesto non esiste (il modello ne ha inventato uno);
            3. l'esecuzione solleva un'eccezione (file assente, Docker spento,
               timeout...).
        In tutti e tre i casi si restituisce un dizionario `{"error": ...}` che
        include il tipo di eccezione e il messaggio. È una scelta deliberata: il
        modello legge quel testo come qualsiasi altra osservazione e può
        correggersi da solo — riformulare gli argomenti, scegliere un altro tool,
        cambiare strategia. È il meccanismo di resilienza del sistema.

        Args:
            tool_call: singola tool call proveniente dall'API.

        Returns:
            Il dizionario prodotto dal tool in caso di successo, oppure un
            dizionario con la sola chiave `error` che descrive il fallimento.
        """
        name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as e:
            log.warning("argomenti JSON non validi per '%s': %s", name, e)
            return {"error": f"argomenti JSON non validi: {e}"}

        tool = self.tool_registry.get(name)
        if tool is None:
            log.warning("tool non trovato: %s", name)
            return {"error": f"tool non trovato: {name}"}

        try:
            return tool.execute(args)
        except Exception as e:
            log.warning("errore eseguendo '%s': %s", name, e)
            return {"error": f"{type(e).__name__}: {e}"}


def _configura_logging():
    """Imposta il logging dell'applicazione.

    La configurazione è applicata qui e non a livello di modulo perché è una
    responsabilità del punto d'ingresso: importare `agent` come libreria non deve
    alterare il logging di chi lo importa.
    """
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Zittisco i log troppo verbosi delle librerie di terze parti
    logging.getLogger("httpx").setLevel(logging.WARNING)


if __name__ == "__main__":
    # Punto d'ingresso manuale: compone le dipendenze concrete (client reale,
    # modello da configurazione, tool con sandbox) e lancia un task di prova che
    # esercita l'intera catena — shell nel container e lettura dal workspace.
    _configura_logging()
    client = OpenAI(base_url=config.ORC2_BASE_URL, api_key=config.ORC2_API_KEY)
    agent = Agent(client, config.ORC2_MODEL, ALL_TOOLS)
    agent.run("usando bash crea il file ciao.txt con dentro 'hello', poi con read_file rileggilo")
