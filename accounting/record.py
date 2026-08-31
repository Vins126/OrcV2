"""Scheda di consumo di una singola chiamata a un modello.

Nota di design (tesi):
    E' una struttura dati **del progetto**, non l'oggetto `usage` restituito
    dall'SDK OpenAI. La differenza conta: cosi' il package di contabilita'
    resta indipendente dalla libreria e dai suoi cambiamenti, e i campi che
    servono a noi (etichetta, latenza, tentativo) convivono con quelli che
    arrivano dal fornitore.

    Il record non sa quanto costa nulla: dice soltanto *quanto e' stato
    consumato*. I prezzi li conosce il registro, la moltiplicazione la fa il
    contabile. Tre responsabilita' separate, tre oggetti distinti.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from accounting.errors import InvalidUsage

@dataclass
class UsageRecord:
    """Cosa ha consumato una singola chiamata a un modello.

    Attributes:
        model: nome del modello, come compare nel registro.
        api_provider: servizio chiamato direttamente dall'applicazione
            (per esempio `litellm` oppure `openai`).
        billing_provider: soggetto che fattura il consumo (per esempio
            `openrouter` oppure `openai`). Entrambi sono metadati di audit,
            non chiavi di prezzo: il listino e' scelto da `model`.
        operation: categoria dell'invocazione (`chat_completion`,
            `image_generation`, `video_generation`...).
        request_id: identificatore della risposta o del job presso il provider.
        status: esito osservato presso il provider.
        dimensions: attributi del prodotto che contestualizzano il prezzo ma
            non sono unita' tariffabili (qualita', risoluzione, durata...).
        measurement_source: `reported` se il provider dichiara l'usage,
            `derived` se e' ricavato da un parametro contrattuale o dall'output,
            `missing` se il provider non ha fornito una misura affidabile.
        quantities: quantita' **fatturabili**, per unita' di consumo. Ogni
            chiave dev'essere un'unita' che ha un prezzo nel registro: e' cio'
            che verra' moltiplicato per il listino. Esempi:
            `{"input_tokens": 350, "output_tokens": 120}` per una chiamata
            testuale, `{"image": 1}` per una generazione di immagine,
            `{"credit": 25}` per un asset 3D.
        cost: costo in dollari. **Lo valorizza il contabile** al momento della
            registrazione, non chi crea il record. Si conserva qui, e non solo
            nei totali, per due ragioni: questa riga finira' su disco nel log
            strutturato e deve potersi leggere da sola; e cosi' il prezzo
            applicato resta congelato a quello valido in quel momento.
        label: a cosa attribuire la spesa (task, sotto-task, ruolo). E' il
            campo che in M4 rendera' i costi imputabili al singolo worker.
        finish_reason: come si e' chiusa la generazione. Il valore `length`
            segnala una risposta **troncata**: e' un segnale di qualita' che
            non costa nulla ottenere, e nella cascade e' motivo di escalation.
        n_tool_calls: quanti tool ha richiesto il modello in questa risposta.
        latency_s: durata della chiamata in secondi.
        attempt: a quale tentativo la chiamata e' riuscita. L'agente ritenta
            con backoff: un successo al terzo tentativo ha caratteristiche
            diverse da uno al primo.
        timestamp: istante della creazione del record, in ISO 8601 UTC.
        reasoning_tokens: token di ragionamento dichiarati dal fornitore.
            **Solo per analisi**, mai per il calcolo del costo.
        notes: annotazione libera.

    ⚠️ Due trappole sul conteggio, da non sbagliare mai:

        `reasoning_tokens` e' **gia' incluso** in `output_tokens`: il fornitore
        lo espone come dettaglio, non come voce aggiuntiva. Sommarlo al costo
        farebbe pagare due volte la parte di ragionamento. Per questo vive
        fuori da `quantities`, dove finisce solo cio' che si moltiplica
        davvero per un prezzo.

        Anche i token serviti dalla cache sono un sottoinsieme di quelli di
        input, ma **hanno una tariffa propria**: vanno scorporati prima di
        costruire il record. Se il fornitore riporta 350 token di input di cui
        200 dalla cache, le quantita' corrette sono
        `{"input_tokens": 150, "cached_input_tokens": 200}` — mai
        `{"input_tokens": 350, "cached_input_tokens": 200}`, che ne conterebbe
        550 e gonfierebbe il totale.
    """

    model: str
    quantities: dict[str, float]

    cost: float = 0.0
    # Identita' dell'operazione. Non appartengono al listino: permettono di
    # correlare il record alla risposta del servizio e di distinguere, per
    # esempio, una chat da una generazione o modifica di immagine.
    api_provider: str | None = None
    billing_provider: str | None = None
    operation: str = "unknown"
    request_id: str | None = None
    status: str = "succeeded"

    # Parametri che spiegano il consumo senza trasformarsi in nuove unita' di
    # prezzo. Esempi: size/quality per immagini, secondi/risoluzione per video.
    # Le unita' fatturabili restano esclusivamente in ``quantities``.
    dimensions: dict[str, Any] = field(default_factory=dict)

    # Dice se le quantita' arrivano dalla risposta del provider (reported), da
    # parametri contrattuali della richiesta (derived), oppure mancano (missing).
    # Cosi' uno usage assente non viene confuso con un consumo pari a zero.
    measurement_source: str = "reported"

    label: str|None = None
    finish_reason: str|None  = None
    n_tool_calls: int = 0
    latency_s: float|None = None
    attempt: int = 1
    timestamp: str = field(default_factory= lambda: datetime.now(timezone.utc).isoformat())
    reasoning_tokens: int = 0
    notes: str|None = None

    def __post_init__(self) -> None:
        """Rifiuta dati impossibili prima che raggiungano listino e ledger."""
        if not self.model.strip():
            raise InvalidUsage("model non puo' essere vuoto")
        if self.measurement_source not in {"reported", "derived", "missing"}:
            raise InvalidUsage("measurement_source deve essere reported, derived o missing")
        for unit, quantity in self.quantities.items():
            if not isinstance(unit, str) or not unit:
                raise InvalidUsage("ogni unita' di consumo deve avere un nome non vuoto")
            if not isinstance(quantity, (int, float)) or isinstance(quantity, bool):
                raise InvalidUsage(f"quantita' non numerica per '{unit}'")
            if not isfinite(quantity) or quantity < 0:
                raise InvalidUsage(f"quantita' non valida per '{unit}': {quantity}")

    @property
    def is_priceable(self) -> bool:
        """Indica se il record ha un prezzo valido."""
        return self.measurement_source != "missing"
