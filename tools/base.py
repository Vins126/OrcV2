"""Contratto astratto dei tool dell'agente.

Definisce cosa significa "essere un tool" nel sistema: le informazioni che ogni
tool deve dichiarare e l'operazione che deve saper eseguire.

Nota di design (tesi):
    È un'applicazione del pattern *Strategy* con classe base astratta. La
    conseguenza architetturale è che l'`Agent` non conosce nessun tool concreto:
    ne riceve una lista e li tratta in modo uniforme. Aggiungere una capacità al
    sistema (una ricerca web, un browser, un linter) non richiede quindi di
    modificare l'agente — è la proprietà che rende praticabile lo swarm (M4),
    dove worker specializzati avranno insiemi di tool diversi.

    La classe separa due responsabilità: ciò che ogni tool deve **dichiarare**
    (nome, descrizione, parametri: informazioni che solo lui conosce) e ciò che
    può **ereditare** (la costruzione dello schema JSON, identica per tutti).
"""

from abc import ABC, abstractmethod

class Tool(ABC):
    """Classe base di ogni strumento utilizzabile dall'agente.

    Le sottoclassi devono implementare le tre proprietà descrittive e il metodo
    `execute`; ricevono in cambio la proprietà `schema` già pronta.
    """

    #CONTRATTI
    @property
    @abstractmethod
    def name(self)-> str:
        """Identificatore univoco del tool.

        È il nome con cui il modello lo invoca e con cui l'`Agent` lo ritrova nel
        proprio registro: deve quindi essere stabile e senza duplicati.
        """
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Descrizione in linguaggio naturale di cosa fa il tool.

        Non è documentazione per il lettore umano ma **prompt per il modello**:
        è l'unica informazione su cui l'LLM si basa per decidere se e quando
        usare questo tool. Una descrizione vaga produce scelte sbagliate.
        """
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """Schema JSON degli argomenti accettati dal tool.

        Segue la specifica JSON Schema attesa dall'API (`type`, `properties`,
        `required`). È il contratto che il modello deve rispettare quando genera
        gli argomenti della chiamata.
        """
        ...

    @abstractmethod
    def execute(self, args: dict) -> dict:
        """Esegue l'operazione del tool.

        Args:
            args: argomenti prodotti dal modello, già deserializzati da JSON.

        Returns:
            Un dizionario serializzabile in JSON con l'esito, che verrà rimandato
            al modello come osservazione.

        Nota:
            Le implementazioni non sono tenute a gestire i propri errori: l'Agent
            cattura le eccezioni e le converte in osservazioni, così il modello
            può leggerle e correggersi (resilienza per auto-correzione).
        """
        ...

    #COMPORTAMENTO CONDIVISO
    @property
    def schema(self) -> dict:
        """Assembla la descrizione del tool nel formato richiesto dall'API.

        Implementato una sola volta qui perché la struttura dell'involucro è
        identica per ogni tool: le sottoclassi forniscono i pezzi, la base li
        compone.

        Returns:
            Il dizionario da inserire nella lista `tools` della chiamata all'LLM.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
