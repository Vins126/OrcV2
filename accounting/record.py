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

@dataclass
class UsageRecord:
    """Cosa ha consumato una singola chiamata a un modello.

    Attributes:
        model: nome del modello, come compare nel registro.
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
    label: str|None = None
    finish_reason: str|None  = None
    n_tool_calls: int = 0
    latency_s: float|None = None
    attempt: int = 1
    timestamp: str = field(default_factory= lambda: datetime.now(timezone.utc).isoformat())
    reasoning_tokens: int = 0
    notes: str|None = None
