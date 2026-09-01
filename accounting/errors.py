"""Eccezioni del package di contabilita'.

Nota di design (tesi):
    Si usano eccezioni proprie invece di `KeyError` o `ValueError` per due
    ragioni. La prima e' diagnostica: un `KeyError: 'gpt5'` non dice se il
    problema sia un modello assente, un'unita' sconosciuta o un file
    malformato, mentre qui il tipo stesso lo dichiara e il messaggio elenca le
    alternative disponibili. La seconda e' di controllo: chi usa il registro
    puo' catturare selettivamente il caso che sa gestire, senza intercettare
    per sbaglio errori di programmazione che devono invece emergere.

    Tutte discendono da `RegistryError`, cosi' un chiamante che voglia trattare
    in blocco "qualunque problema del registro" ha un solo tipo da nominare.
"""


class RegistryError(Exception):
    """Radice di tutti gli errori del registro dei modelli."""


class MalformedRegistry(RegistryError):
    """La configurazione e' incoerente o incompleta.

    Sollevata al **caricamento**, mai durante l'uso: e' il principio del
    fail-fast gia' adottato in `config.richiedi_env`. Un prezzo negativo o
    un'unita' non dichiarata scoperti a meta' di una campagna sperimentale
    invaliderebbero misure gia' pagate; scoperti all'avvio costano un secondo.
    """


class ModelNotFound(RegistryError):
    """E' stato richiesto un modello che il registro non conosce.

    Sollevata al **lookup**: e' un errore d'uso, non di configurazione.
    """


class UnitNotFound(RegistryError):
    """Il modello non espone un prezzo per l'unita' di consumo richiesta.

    Sollevata al **lookup**. Distinta da `ModelNotFound` perche' la causa e'
    diversa: il modello esiste, ma non fattura quel tipo di consumo (chiedere
    il prezzo per immagine a un modello di solo testo, per esempio).
    """

class UnpricedUsage(RegistryError):
    """Il consumo non ha una misura sufficientemente affidabile per il prezzo.

    Non equivale a un consumo gratuito: il provider non ha restituito l'usage
    necessario per calcolarne il costo in modo riproducibile.
    """

class RoleNotFound(RegistryError):
    """E' stato richiesto un ruolo che il registro non conosce.

    Sollevata al **lookup**, come `ModelNotFound`: la configurazione e'
    valida: e' il chiamante ad aver chiesto un mestiere che nessuno ha
    dichiarato in `[roles]`.
    """


class CapabilityUnavailable(RegistryError):
    """Nessun modello del pool offre la capacita' richiesta.

    Distinta da `MalformedRegistry` perche' non c'e' nulla di sbagliato nel
    file: il listino e' coerente, semplicemente il pool non copre quel
    bisogno. Si corregge aggiungendo un modello, non riparando una riga.

    Distinta anche da una lista vuota restituita da `models_with`: li'
    l'assenza e' un'informazione da interpretare, qui e' un impedimento.
    """


class InvalidUsage(ValueError):
    """Un UsageRecord contiene quantita' non valide per la contabilita'."""
