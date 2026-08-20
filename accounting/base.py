"""Contratto del contabile dei costi.

Nota di design (tesi):
    Il contabile e' l'unico punto del sistema che sa *quanto si e' speso*. Il
    registro sa quanto costano le cose, il record dice quanto se n'e' usato:
    qui i due si incontrano e diventano un totale.

    Come per `Tool` e `CommandExecutor`, si dichiara prima l'interfaccia e poi
    le implementazioni. Serve gia' adesso per i test — un contabile finto
    permette di verificare che l'agente *registri* i consumi senza tirare in
    ballo prezzi veri — e servira' in M4, dove accanto al contabile in memoria
    di ogni worker comparira' un contabile aggregante che somma quelli della
    squadra.

    L'interfaccia dichiara solo cio' che **ogni** contabile deve saper fare:
    accettare un consumo e dire quanto si e' speso. Il **dettaglio per
    chiamata** vive nelle implementazioni concrete e non qui, perche' un
    contabile aggregante non ha record propri: somma quelli dei figli.
    Metterlo nel contratto lo obbligherebbe ad averli.
"""

from abc import ABC, abstractmethod
from accounting.record import UsageRecord

class Accountant(ABC):
    """Cio' che ogni contabile dei costi deve saper fare."""

    @abstractmethod
    def register(self, record: UsageRecord) -> float:
        """Contabilizza un consumo e ne restituisce il costo.

        L'implementazione deve valorizzare il campo `cost` del record: chi lo
        crea non conosce i prezzi, li conosce solo il contabile tramite il
        registro.

        Args:
            record: la scheda della chiamata da contabilizzare.

        Returns:
            Il costo in dollari della **singola** chiamata registrata.
            Restituirlo evita al chiamante di dover calcolare la differenza
            fra due totali per sapere quanto e' costato l'ultimo passo:
            informazione che serve al guardiano del budget (M2a.5).
        """
        ...

    @property
    @abstractmethod
    def total_cost(self) -> float:
        """Costo complessivo in dollari di quanto registrato finora.

        E' una proprieta' e non un metodo perche' descrive uno **stato**, non
        un'azione. Che il valore sia gia' pronto o venga ricalcolato a ogni
        lettura resta un dettaglio dell'implementazione, invisibile a chi lo
        usa: si potra' cambiare strategia senza toccare il codice chiamante.
        """
        ...

    @property
    @abstractmethod
    def call_count(self) -> int:
        """Numero di chiamate registrate finora.

        Serve al report di fine task e alle medie della campagna sperimentale
        (`total_cost / call_count` = costo medio per chiamata). E' anche un
        controllo di coerenza: se non corrisponde alle iterazioni del ciclo
        ReAct, qualche consumo non sta venendo registrato.
        """
        ...