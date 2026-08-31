"""Registro dei modelli: prezzi, capacita' e costi di accesso.

Traduce il file di configurazione `models.toml` in un oggetto interrogabile,
e fa da unico punto del sistema che conosce la struttura di quel file.

Nota di design (tesi):
    Il registro e' **passivo e immutabile**: non sa che esistano chiamate a
    modelli, non accumula nulla, risponde e dimentica. Chi tiene i conti e'
    il contabile, che consulta il registro quando ha bisogno di un prezzo.
    La separazione segue il criterio "cosa cambia per quale ragione": la
    politica di prezzo (sconti, fasce, tariffe cache) varia con i listini dei
    fornitori, la contabilita' varia con cio' che si vuole misurare.

    Da questa immutabilita' discende una proprieta' utile a M3/M4: **un solo
    registro condiviso da N contabili**, uno per agente. Il file si legge una
    volta sola e i costi restano attribuibili al singolo worker, mentre se
    ogni contabile leggesse il TOML per conto proprio si avrebbero N copie
    identiche degli stessi prezzi.

    Il calcolo del costo vive qui e non nel contabile perche' la *base* di
    prezzo (§ sezione `[units]` del file) e' un dettaglio di come i listini
    sono espressi: il contabile non ha motivo di conoscerla, e se domani i
    prezzi si complicassero (sconti a volume, promozioni) la complessita'
    resterebbe confinata in questa classe.
"""

import tomllib
from math import isfinite

from accounting.errors import MalformedRegistry, ModelNotFound, UnitNotFound

#: Capacita' riconosciute, dalla tassonomia di `PIANO_completo.md` §3.11.
#: Vive nel codice e non nella configurazione perche' e' un elemento del
#: modello di dominio, non un parametro: introdurre una capacita' nuova
#: richiede comunque di scrivere il codice che sa invocarla. Validare i nomi
#: contro questa lista intercetta i refusi (`"embeding"`) che altrimenti
#: renderebbero un modello invisibile al filtro per capacita'.
CAPACITA_NOTE = frozenset({
    "reasoning",     # C1  pianificazione, decomposizione
    "code",          # C2  generazione di codice (incluso l'SVG, che e' codice)
    "text",          # C3  scrittura di contenuti
    "vision_input",  # C4  lettura di immagini: mockup, screenshot
    "image_gen",     # C5  generazione di immagini raster
    "video_gen",     # C7  generazione di video
    "model_3d",      # C8  generazione di asset 3D
    "tts",           # C9  sintesi vocale
    "stt",           # C10 trascrizione
    "embedding",     # C11 vettori per RAG e per il router
    "rerank",        # C12 riordino per rilevanza
})


class ModelRegistry:
    """Listino consultabile dei modelli disponibili al sistema.

    Attributes:
        units: mappa unita' -> base di prezzo (a quante unita' si riferisce il
            prezzo dichiarato: 1_000_000 per i token, 1 per le immagini).
        providers: mappa fornitore -> dati del fornitore (costi di accesso).
        models: mappa modello -> dati del modello (provider, capacita', prezzi).
    """

    def __init__(self, data: dict):
        """Valida la configurazione gia' letta e la conserva.

        Riceve un dizionario invece di un percorso cosi' che i test possano
        costruire un registro senza toccare il filesystem; per caricarlo da
        file si usa `from_file`.

        Args:
            data: configurazione con le sezioni `units`, `providers`, `models`.

        Raises:
            MalformedRegistry: se la configurazione e' incoerente. La verifica
                e' esaustiva e avviene qui, una volta sola: dopo la
                costruzione il registro e' garantito consistente.
        """
        self.units = data.get("units", {})
        self.providers = data.get("providers", {})
        self.models = data.get("models", {})
        self._valida()

    @classmethod
    def from_file(cls, path):
        """Costruisce il registro leggendo un file TOML.

        Args:
            path: percorso del file di configurazione.

        Returns:
            Un `ModelRegistry` validato.

        Raises:
            MalformedRegistry: se il file non e' TOML valido o se il contenuto
                non supera la validazione.
            OSError: se il file non esiste o non e' leggibile.
        """
        with open(path, "rb") as f:
            try:
                data = tomllib.load(f)
            except tomllib.TOMLDecodeError as e:
                raise MalformedRegistry(f"{path}: TOML non valido: {e}") from e
        return cls(data)

    # ── Interrogazioni ────────────────────────────────────────────────────

    def cost(self, model: str, unit: str, quantity: float) -> float:
        """Calcola il costo in dollari di un consumo.

        Applica la formula unica valida per ogni unita' di fatturazione:

            costo = quantita' / base * prezzo

        dove la base viene dalla sezione `[units]`. E' cio' che permette di
        trattare allo stesso modo i token (prezzo per milione) e le immagini o
        i crediti (prezzo per pezzo), senza che il chiamante debba sapere
        quale scala si applichi.

        Args:
            model: nome del modello, come compare nel registro.
            unit: unita' di consumo (es. `input_tokens`, `image`, `credit`).
            quantity: quantita' consumata, nella sua unita' naturale.

        Returns:
            Il costo in dollari.

        Raises:
            ModelNotFound: se il modello non e' a registro.
            UnitNotFound: se il modello non espone un prezzo per quell'unita'.
        """
        if not self._is_finite_number(quantity) or quantity < 0:
            raise ValueError(f"quantita' non valida per '{unit}': {quantity}")
        prezzi = self._modello(model).get("prices", {})
        if unit not in prezzi:
            raise UnitNotFound(
                f"il modello '{model}' non ha un prezzo per l'unita' '{unit}'; "
                f"unita' disponibili per questo modello: {self._elenca(prezzi)}"
            )
        return quantity / self.units[unit] * prezzi[unit]

    def models_with(self, capability: str) -> list[str]:
        """Elenca i modelli che offrono una data capacita'.

        E' il supporto al capability-aware routing (M2s): il filtro per
        capacita' precede quello sul costo, perche' un modello privo della
        capacita' richiesta non e' confrontabile sul prezzo per quanto
        economico sia.

        Args:
            capability: nome della capacita' (vedi `CAPACITA_NOTE`).

        Returns:
            I nomi dei modelli che la offrono, in ordine alfabetico. Lista
            vuota se nessuno la offre: non e' un errore, e' un'informazione
            che spetta al chiamante interpretare.
        """
        return sorted(
            nome for nome, dati in self.models.items()
            if capability in dati.get("capabilities", [])
        )

    def monthly_fee(self, provider: str) -> float:
        """Costo fisso mensile di un fornitore (decisione D12).

        Non entra nel costo per chiamata: e' un costo affondato che non varia
        con le decisioni del router e non deve quindi influenzarle. Va pero'
        dichiarato a parte, altrimenti il costo complessivo del sistema
        risulterebbe sottostimato.

        Args:
            provider: nome del fornitore.

        Returns:
            Il canone mensile in dollari (0.0 per i fornitori a consumo).

        Raises:
            ModelNotFound: se il fornitore non e' a registro.
        """
        if provider not in self.providers:
            raise ModelNotFound(
                f"fornitore '{provider}' non a registro; "
                f"disponibili: {self._elenca(self.providers)}"
            )
        return self.providers[provider].get("monthly_fee", 0.0)

    # ── Interni ───────────────────────────────────────────────────────────

    def _modello(self, model: str) -> dict:
        """Restituisce i dati di un modello, o solleva un errore parlante."""
        if model not in self.models:
            raise ModelNotFound(
                f"modello '{model}' non a registro; "
                f"disponibili: {self._elenca(self.models)}"
            )
        return self.models[model]

    @staticmethod
    def _elenca(nomi) -> str:
        """Formatta un elenco di nomi per i messaggi d'errore."""
        return ", ".join(sorted(nomi)) if nomi else "(nessuno)"

    def _valida(self):
        """Verifica la coerenza dell'intera configurazione.

        Cinque controlli, tutti bloccanti. Il registro e' il guardiano della
        correttezza dei prezzi: un dato sbagliato che passi di qui si
        propagherebbe silenziosamente a ogni misura della campagna
        sperimentale, e un costo negativo o un'unita' senza base non
        produrrebbero un errore ma un *numero sbagliato* — il tipo di guasto
        peggiore, perche' non si manifesta.

        Raises:
            MalformedRegistry: al primo problema incontrato, con l'indicazione
                del modello e del campo responsabili.
        """
        for base in self.units.values():
            if not self._is_finite_number(base) or base <= 0:
                raise MalformedRegistry(
                    f"le basi in [units] devono essere positive, trovato {base}"
                )

        for nome, dati in self.models.items():
            provider = dati.get("provider")
            if provider not in self.providers:
                raise MalformedRegistry(
                    f"modello '{nome}': fornitore '{provider}' non dichiarato in "
                    f"[providers]; senza di esso i costi di accesso non sono "
                    f"attribuibili. Dichiarati: {self._elenca(self.providers)}"
                )

            for capacita in dati.get("capabilities", []):
                if capacita not in CAPACITA_NOTE:
                    raise MalformedRegistry(
                        f"modello '{nome}': capacita' '{capacita}' sconosciuta; "
                        f"riconosciute: {self._elenca(CAPACITA_NOTE)}"
                    )

            prezzi = dati.get("prices", {})
            if not prezzi:
                raise MalformedRegistry(
                    f"modello '{nome}': nessun prezzo dichiarato in [prices]"
                )

            for unita, prezzo in prezzi.items():
                if unita not in self.units:
                    raise MalformedRegistry(
                        f"modello '{nome}': l'unita' '{unita}' non e' dichiarata in "
                        f"[units], quindi manca la base con cui calcolare il costo. "
                        f"Dichiarate: {self._elenca(self.units)}"
                    )
                if not self._is_finite_number(prezzo) or prezzo < 0:
                    raise MalformedRegistry(
                        f"modello '{nome}': prezzo negativo per '{unita}' ({prezzo})"
                    )

    @staticmethod
    def _is_finite_number(value: object) -> bool:
        """Accetta solo numeri reali finiti, escludendo booleani mascherati da int."""
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(value)
        )
