"""Verdetti del rilevatore di loop.

Definisce il vocabolario con cui il `RilevatoreLoop` comunica all'`Agent` cosa
fare quando sospetta che il modello sia bloccato in un ciclo improduttivo.

Nota di design (tesi):
    Si è scelto un `Enum` invece di un booleano ("è in loop sì/no") perché la
    risposta corretta a un loop non è binaria. Un modello che ripete due volte la
    stessa azione può essere legittimamente in attesa di qualcosa; un modello che
    la ripete sette volte no. L'enum codifica quindi una **escalation graduale**
    (procedi → avvisa → interrompi), che è la stessa forma logica della
    *cascade* di M2: osserva un segnale, e reagisci in modo proporzionato.

    Ogni verdetto trasporta anche i dati necessari ad agire (`ferma`, `avviso`),
    così l'Agent non deve contenere una tabella di corrispondenze parallela.
"""

from enum import Enum

class Alerts(Enum):
    """Esito del controllo anti-loop su un gruppo di tool call.

    Ogni membro dell'enum è una coppia `(ferma, avviso)` che viene espansa dal
    costruttore in due attributi leggibili.

    Attributes:
        ferma: True se il task va interrotto immediatamente.
        avviso: testo da iniettare nella conversazione come richiamo per il
            modello, oppure None se non c'è nulla da comunicare.

    Members:
        OK: nessuna ripetizione sospetta, si prosegue normalmente.
        AVVISA: ripetizione sospetta; il task continua ma il modello riceve un
            richiamo esplicito per dargli modo di cambiare strategia.
        FERMA: ripetizione persistente; il task viene interrotto.
    """
    OK     = (False, None)
    AVVISA = (False, "ATTENZIONE: stai ripetendo la stessa azione senza progresso. Cambia approccio o fermati.")
    FERMA  = (True,  None)

    def __init__(self, ferma, avviso):
        """Espande la tupla del membro enum in attributi con nome.

        Args:
            ferma: flag di interruzione del task.
            avviso: messaggio di richiamo per il modello (o None).
        """
        self.ferma = ferma
        self.avviso = avviso
