"""Contratto astratto degli esecutori di comandi.

Definisce l'interfaccia comune a tutti i modi in cui un comando shell può essere
eseguito, permettendo di sostituire l'ambiente di esecuzione senza che il codice
chiamante se ne accorga.

Nota di design (tesi):
    L'astrazione isola la **decisione di sicurezza** dal resto del sistema. Il
    tool `bash` conosce solo questa interfaccia; sapere se il comando finirà in
    un container effimero o sulla macchina dello sviluppatore non lo riguarda.
    Questo rende l'isolamento una variabile sperimentale controllabile — utile
    perché nella tesi la sandbox non serve solo a proteggere, ma anche a
    garantire che ogni misura di costo e qualità avvenga in un ambiente
    identico e ripetibile.
"""

from abc import ABC, abstractmethod

class CommandExecutor(ABC):
    """Interfaccia di un ambiente capace di eseguire comandi shell."""

    @abstractmethod
    def run(self, command: str) -> dict:
        """Esegue un comando e ne riporta l'esito.

        Args:
            command: comando shell da eseguire.

        Returns:
            Un dizionario con `stdout`, `stderr` ed `exit_code`. Il formato è
            fisso per tutte le implementazioni: è ciò che consente di scambiarle
            fra loro senza modificare i chiamanti.
        """
        ...
