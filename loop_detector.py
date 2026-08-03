"""Rilevamento dei cicli improduttivi dell'agente.

Un agente ReAct può entrare in un ciclo in cui ripete all'infinito la stessa
azione — tipicamente quando un tool restituisce un errore che il modello non sa
interpretare, e che quindi riprova identico. Senza un rilevatore, il ciclo si
ferma solo al tetto di iterazioni, dopo aver consumato token (e denaro) inutili.

Nota di design (tesi):
    Questo modulo è la forma più semplice del pattern che regge tutta la tesi:
    **osserva un segnale di (non-)progresso e agisci di conseguenza.** Qui il
    segnale è sintattico e gratuito (le azioni sono identiche?); in M2 lo stesso
    schema riapparirà con un segnale semantico e costoso (la qualità
    dell'output regge la soglia τ?) per decidere l'escalation di modello.
    In altre parole: il rilevatore di loop è il "giudice" dei poveri, e occupa
    nell'architettura esattamente la posizione che occuperà il giudice di qualità.
"""

from alerts import Alerts


class RilevatoreLoop:
    """Conta le ripetizioni consecutive di azioni identiche e ne dà un verdetto.

    Mantiene lo stato di una singola esecuzione di task: va quindi istanziato
    una volta per task, non una volta per agente.

    Attributes:
        soglia_avviso: numero di ripetizioni identiche che fa scattare AVVISA.
        soglia_stop: numero di ripetizioni identiche che fa scattare FERMA.
        ultima_firma: firma dell'ultimo gruppo di tool call osservato.
        ripetizioni: quante volte consecutive è comparsa `ultima_firma`.

    Limite noto:
        Il confronto è solo con l'iterazione **immediatamente precedente**:
        rileva cicli A→A→A ma non cicli alternati A→B→A→B. Per coprirli
        servirebbe una finestra di storia più lunga.
    """

    def __init__(self, soglia_avviso=4, soglia_stop=7):
        """Inizializza il rilevatore con le due soglie di escalation.

        Args:
            soglia_avviso: ripetizioni identiche oltre le quali avvisare il modello.
            soglia_stop: ripetizioni identiche oltre le quali interrompere il task.
        """
        self.soglia_avviso = soglia_avviso
        self.soglia_stop = soglia_stop
        self.ultima_firma = None
        self.ripetizioni = 0

    def in_loop_verdict(self, tool_calls) -> Alerts:
        """Registra un nuovo gruppo di tool call e restituisce il verdetto.

        La "firma" di un'iterazione è la tupla dei `(nome_tool, argomenti)`
        richiesti. Si confrontano gli argomenti in forma di stringa grezza, così
        come arrivano dall'API: due chiamate sono considerate identiche solo se
        il modello ha prodotto esattamente lo stesso testo. Se la firma coincide
        con quella precedente il contatore avanza, altrimenti riparte da uno
        (qualunque azione diversa è considerata progresso).

        Args:
            tool_calls: lista di tool call dell'iterazione corrente, nel formato
                dell'API OpenAI (serve `.function.name` e `.function.arguments`).

        Returns:
            `Alerts.FERMA` se la soglia di stop è stata raggiunta o superata,
            `Alerts.AVVISA` **esattamente** alla soglia di avviso (l'avviso è
            volutamente emesso una sola volta, per non inondare il contesto di
            richiami ripetuti), `Alerts.OK` in tutti gli altri casi.
        """
        firma = tuple((tc.function.name, tc.function.arguments) for tc in tool_calls)
        if firma == self.ultima_firma:
            self.ripetizioni += 1
        else:
            self.ripetizioni = 1
            self.ultima_firma = firma

        #Se chiamata BLOCCANTE
        if self.ripetizioni >= self.soglia_stop:
            return Alerts.FERMA
        #Se avviso potenziale loop
        if self.ripetizioni == self.soglia_avviso:
            return Alerts.AVVISA


        return Alerts.OK
