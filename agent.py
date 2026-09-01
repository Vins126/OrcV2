"""Nucleo ReAct: decide, invoca tool e restituisce un esito strutturato.

Questo modulo non conosce SDK, chiavi API, listini o filesystem di persistenza.
Riceve un `ChatGateway` e tool gia' costruiti dal punto d'ingresso; per questo e'
facile da testare e riutilizzare con provider o ruoli diversi.
"""

import json
import logging
from dataclasses import dataclass

import config
from alerts import Alerts
from budget_guard import BudgetExceeded
from llm_contracts import AssistantTurn, ChatGateway
from loop_detector import RilevatoreLoop

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


class AgentFailure(Exception):
    """Errore inatteso durante una run, con il conteggio delle iterazioni svolte.

    Serve a non perdere un dato che esiste solo dentro il ciclo: quando
    un'eccezione lo attraversa, il numero di iterazioni gia' compiute andrebbe
    perduto e il ledger registrerebbe `iterations: 0` anche per una run che
    aveva gia' lavorato e speso. Il conteggio viaggia quindi con l'eccezione
    invece di stare in un attributo dell'agente: un attributo condiviso
    sarebbe scorretto in M4, dove lo stesso agente puo' servire piu' run.

    Attributes:
        iterations: iterazioni completate prima del guasto.
        cause_type: nome della classe dell'eccezione originale, da registrare
            nel ledger al posto di questo involucro.
    """

    def __init__(self, iterations: int, cause: BaseException):
        """Compone il messaggio e conserva il conteggio delle iterazioni.

        Args:
            iterations: iterazioni completate prima del guasto.
            cause: l'eccezione originale. Se ne conserva il nome della classe per
                registrare nel ledger la causa vera, non questo involucro.
        """
        super().__init__(
            f"run interrotta da {type(cause).__name__} "
            f"all'iterazione {iterations}"
        )
        self.iterations = iterations
        self.cause_type = type(cause).__name__


@dataclass(frozen=True)
class RunResult:
    """Esito strutturato di una run dell'agente.

    Il valore e' separato dai messaggi stampati perche' il chiamante (oggi il
    ledger, domani l'orchestratore) deve poter registrare la fine della run
    senza analizzare testo destinato a un essere umano.
    """

    status: str
    iterations: int
    final_message: str | None = None


class Agent:
    """Modello linguistico in un ciclo ReAct, dotato di strumenti.

    Le dipendenze (gateway del modello, tool) sono iniettate dall'esterno
    anziché costruite internamente. Ne derivano due proprietà: la classe è
    testabile con un gateway finto, senza chiamate di rete né costi; ed è
    riutilizzabile con modelli e set di strumenti diversi, che è il
    presupposto del routing per ruolo (M2s) e dello swarm (M4).

    Attributes:
        llm: confine che invoca il modello, senza esporre SDK o prezzi.
        tools: strumenti messi a disposizione del modello.
        tool_schemas: descrizioni dei tool nel formato atteso dall'API.
        tool_registry: mappa nome→tool, per ritrovare lo strumento richiesto
            dal modello in tempo costante.
    """

    def __init__(self, llm: ChatGateway, tools):
        """Registra le dipendenze e precalcola le strutture di lookup.

        Schemi e registro sono costruiti una sola volta qui, non a ogni
        iterazione: sono invarianti per tutta la vita dell'agente.

        Args:
            llm: gateway del modello (o un suo sostituto nei test).
            tools: lista di istanze di `tools.base.Tool`.
        """
        self.llm = llm
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
            try:
                status, final_message = self._esegui_iterazione(messages, rilevatore, iterazione)
            except Exception as errore:
                # Gli esiti previsti (budget, servizio giu') sono gia' gestiti
                # dentro l'iterazione: qui arriva solo cio' che non era atteso.
                # Non lo si nasconde — resta un difetto da correggere — ma gli
                # si allega il numero di iterazioni, altrimenti perduto.
                raise AgentFailure(iterazione, errore) from errore
            if status is not None:
                return RunResult(status=status, iterations=iterazione, final_message=final_message)

        log.error("Raggiunto il limite di %d iterazioni", max_iterations)
        return RunResult(
            status="max_iterations", iterations=max_iterations,
            final_message=f"Limite di {max_iterations} iterazioni raggiunto.",
        )

    def _esegui_iterazione(
        self, messages, rilevatore, iterazione
    ) -> tuple[str | None, str | None]:
        """Esegue un passo ReAct e restituisce l'esito terminale, se presente.

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
            Una coppia ``(stato, messaggio)``. Lo stato e' ``None`` se il ciclo
            deve proseguire; altrimenti il messaggio e' destinato al chiamante,
            che decide come mostrarlo all'utente.
        """
        try:
            msg = self._chiama_llm(messages)
        except BudgetExceeded:
            log.warning("Interrompo il task: budget esaurito")
            return "budget_exhausted", "Budget della run esaurito: nessuna nuova chiamata effettuata."
        except RuntimeError as e:
            log.error("Interrompo il task: %s", e)
            return "service_unavailable", "Servizio LLM non raggiungibile. Riprova più tardi."

        # L'AI non chiede tool -> ha finito
        if not msg.tool_calls:
            log.info("Task completato in %d iterazioni", iterazione)
            return "completed", msg.content

        # Rilevo loop per evitare sprechi
        verdetto = rilevatore.in_loop_verdict(msg.tool_calls)
        if verdetto == Alerts.FERMA:
            log.error("Loop persistente (%d ripetizioni): interrompo", rilevatore.ripetizioni)
            return "loop_detected", "Loop persistente: non sono riuscito a risolvere il problema."

        # L'AI chiede tool -> li eseguo
        messages.append(msg)
        self._esegui_tool_calls(messages, msg)

        # Potenziale loop -> avviso il modello e gli do una chance
        if verdetto == Alerts.AVVISA:
            log.warning("Possibile loop (%d ripetizioni): avviso il modello", rilevatore.ripetizioni)
            messages.append({"role": "user", "content": verdetto.avviso})

        return None, None

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
        """Chiede il messaggio successivo al gateway del modello.

        Il gateway incapsula SDK, retry, misurazione e accounting; qui resta
        soltanto l'azione necessaria al ciclo ReAct.

        Args:
            messages: conversazione completa da inviare al modello.

        Returns:
            Un `AssistantTurn`: cio' che il modello ha prodotto, senza traccia
            dell'SDK che glielo ha chiesto.

        Raises:
            RuntimeError: se tutti i tentativi falliscono. È un'eccezione distinta
                e volutamente generica: al chiamante interessa solo che il
                servizio non sia raggiungibile, non quale errore di rete sia
                occorso.
            BudgetExceeded: se il tetto di spesa era già raggiunto prima della
                chiamata. Non è un guasto: è una terminazione voluta.
        """
        msg = self.llm.complete(messages, self.tool_schemas)
        self._log_risposta(msg)
        return msg

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
                      [tc.name for tc in msg.tool_calls])
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
                      tool_call.name, tool_call.arguments, risultato)
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
        name = tool_call.name
        try:
            args = json.loads(tool_call.arguments)
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


if __name__ == "__main__":
    # Compatibilita' con il comando storico `python agent.py`.
    from main import main

    raise SystemExit(main())
