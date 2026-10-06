"""Fabbrica di agenti: dato un ruolo, costruisce un agente persistente.

Fino a M2s.2 la catena di montaggio di un agente — modello, client, contabile,
gateway, strumenti — era scritta a mano in `main.py`, e valeva per un agente
solo. Qui la stessa catena e' parametrizzata sul **ruolo**: si dice "worker" e
si ottiene un agente col modello che il registro assegna a quel ruolo,
raggiunto attraverso il suo fornitore.

Nota di design (tesi):
    **Un agente e' persistente.** Ha la propria finestra di contesto, che
    cresce incarico dopo incarico, e vive finche' chi lo ha creato (in futuro
    l'orchestratore) non decide di eliminarlo con `dismiss`. Un agente non e'
    quindi "una run": e' un dipendente a cui si danno piu' incarichi.

    Da qui la struttura dei dati:
      - il **contabile** e' uno per agente e somma la spesa di tutta la sua
        vita;
      - il **ledger** e' uno per **incarico**: ogni task assegnato e' una run
        completa e chiusa, con il proprio `summary.json`. E' cio' che permette
        di conoscere il costo di ciascun task (la metrica CPT-tau lo richiede)
        e di estrarre dal log una riga per sotto-task (il dataset del router).
        Tutti i ledger di un agente portano lo stesso `agent_id`.

    Il registro dei modelli e' **uno solo e condiviso** fra tutti gli agenti: e'
    di sola lettura dopo la validazione. Tutto il resto e' **per agente** —
    contabile, workspace, guardiano del budget — perche' sono i punti in cui
    due agenti, se condividessero lo stato, si sporcherebbero a vicenda: costi
    mescolati, file corrotti, un tetto consumato da chi non l'ha speso. E' la
    decisione che in M3 (parallelismo) evita il problema invece di doverlo
    risolvere.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple
from uuid import uuid4

import anthropic
import openai

import config
from accounting import InMemoryAccountant, ModelRegistry
from accounting.ledger import RunLedger
from accounting.ledger_accountant import LedgerAccountant
from agent import Agent, RunResult
from budget_guard import BudgetGuard
from llm_gateway import AnthropicChatGateway, ChatGatewayBase, OpenAIChatGateway
from run_reporter import RunReporter
from run_session import RunSession
from tools import build_default_tools


class UnsupportedProvider(Exception):
    """Il modello del ruolo appartiene a un fornitore senza gateway di chat.

    Distinta dagli errori del registro perche' il registro e' coerente: il
    modello esiste e il suo fornitore e' dichiarato. Manca un pezzo di
    questo modulo — per esempio `tripo`, che genera asset 3D e non conversa.
    """


class AgentDismissed(Exception):
    """Si e' tentato di assegnare un incarico a un agente gia' eliminato."""


class Backend(NamedTuple):
    """Come si parla con un fornitore: quale gateway e quale client.

    Attributes:
        gateway: classe di gateway che traduce fra il progetto e il provider.
        make_client: funzione che costruisce il client dell'SDK a partire dalle
            credenziali del fornitore.
    """

    gateway: type[ChatGatewayBase]
    make_client: Callable[[config.ProviderCredentials], Any]


def _client_anthropic(credenziali: config.ProviderCredentials) -> Any:
    """Costruisce il client dell'SDK Anthropic.

    `base_url` puo' essere `None`: in quel caso l'SDK usa il proprio endpoint
    di default, che e' la scelta giusta per i fornitori che non hanno bisogno
    di un indirizzo particolare.
    """
    return anthropic.Anthropic(
        api_key=credenziali.api_key, base_url=credenziali.base_url)


def _client_openai(credenziali: config.ProviderCredentials) -> Any:
    """Costruisce il client dell'SDK OpenAI.

    Serve anche ai fornitori che ne adottano il formato `chat.completions` con
    un proprio indirizzo (Moonshot, MiniMax): cambia solo `base_url`.
    """
    return openai.OpenAI(
        api_key=credenziali.api_key, base_url=credenziali.base_url)


#: Per ogni fornitore, come raggiungerlo. Le chiavi sono i nomi dichiarati in
#: `[providers.*]` di `models.toml`. Piu' fornitori possono puntare alla stessa
#: classe di gateway: Moonshot e MiniMax parlano lo stesso formato di OpenAI e
#: differiscono solo per indirizzo e chiave, che arrivano dal registro.
BACKEND_PER_PROVIDER: dict[str, Backend] = {
    "anthropic": Backend(AnthropicChatGateway, _client_anthropic),
    "openai": Backend(OpenAIChatGateway, _client_openai),
    "moonshot": Backend(OpenAIChatGateway, _client_openai),
    "minimax": Backend(OpenAIChatGateway, _client_openai),
}


@dataclass
class BuiltAgent:
    """Un agente persistente, con cio' che serve per assegnargli incarichi e leggerne i costi.

    `Agent` non espone il proprio contabile ne' i propri ledger, ma a fine
    incarico qualcuno deve leggere il costo. Farli viaggiare insieme all'agente
    evita di doverli cercare altrove: in M3, sommare i costi di una squadra
    diventa un ciclo su queste strutture.

    Attributes:
        agent: l'agente, con la sua conversazione che persiste.
        gateway: il suo gateway verso il fornitore (serve a ricollegare gli
            eventi tecnici al ledger dell'incarico in corso).
        accountant: il suo contabile: somma la spesa di tutta la sua vita.
        agent_id: identificativo dell'agente, uguale in tutti i suoi ledger.
        role: il ruolo per cui e' stato costruito.
        model: chiave del modello nel registro (non il nome del fornitore).
        workspace: cartella in cui l'agente puo' scrivere, solo sua e valida
            per tutta la sua vita.
        open_ledger: crea il ledger di un nuovo incarico dato il task.
        reporter: chi emette il rapporto a fine incarico; `None` usa quello
            di default.
        ledgers: i ledger degli incarichi svolti finora, in ordine. E' il
            "fascicolo" che collega l'agente alle sue run.
        dismissed: vero dopo `dismiss`.
    """

    agent: Agent
    gateway: ChatGatewayBase
    accountant: LedgerAccountant
    agent_id: str
    role: str
    model: str
    workspace: Path
    open_ledger: Callable[[str], RunLedger] = field(repr=False)
    reporter: RunReporter | None = field(default=None, repr=False)
    ledgers: list[RunLedger] = field(default_factory=list)
    dismissed: bool = False

    def assign(self, task: str, max_iterations: int | None = None) -> RunResult:
        """Assegna un incarico all'agente e lo esegue.

        Ogni incarico e' una run completa: ha il proprio ledger, che viene
        chiuso in ogni esito, eccezioni comprese (se ne occupa `RunSession`).
        La conversazione dell'agente invece prosegue: ricorda gli incarichi
        precedenti. E il contabile continua a sommare, quindi il costo
        dell'incarico si legge nel summary del suo ledger e quello dell'intera
        vita dell'agente in `accountant.total_cost`.

        Args:
            task: testo del compito.
            max_iterations: tetto di iterazioni per questo incarico.

        Returns:
            L'esito strutturato dell'incarico.

        Raises:
            AgentDismissed: se l'agente e' stato eliminato.
        """
        if self.dismissed:
            raise AgentDismissed(
                f"l'agente '{self.agent_id}' e' stato eliminato e non accetta "
                f"altri incarichi"
            )

        ledger = self.open_ledger(task)
        self.ledgers.append(ledger)
        # Il contabile e il gateway scrivono nel ledger di QUESTO incarico: il
        # primo i consumi, il secondo gli eventi tecnici (errori del provider,
        # soglie di budget). Senza ricollegarli finirebbero in quello del
        # precedente, gia' chiuso.
        self.accountant.attach(ledger)
        self.gateway.event_sink = ledger
        return RunSession(self.agent, ledger, self.reporter).run(
            task, max_iterations=max_iterations)

    def dismiss(self) -> dict[str, Any]:
        """Elimina l'agente: non accettera' altri incarichi.

        Restituisce un riepilogo minimo della sua vita. E' solo il nucleo di
        cio' che servira': le regole con cui l'orchestratore decide la chiusura
        e il fascicolo da lasciare per poter recuperare in seguito le
        informazioni cruciali — la conversazione compresa — sono ancora da
        progettare (ROADMAP, M4.2b).

        Returns:
            Identita' dell'agente, numero di incarichi, elenco delle run e
            costo totale della sua vita.
        """
        self.dismissed = True
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "model": self.model,
            "assignments": len(self.ledgers),
            "run_ids": [ledger.run_id for ledger in self.ledgers],
            "total_cost": self.accountant.total_cost,
        }


class AgentFactory:
    """Costruisce agenti per ruolo, ciascuno con le proprie risorse.

    Il costruttore riceve cio' che e' **uguale per tutti** gli agenti; `build`
    riceve cio' che **cambia**. Se un domani si volesse passare a `build` un
    valore identico per tutti, il posto giusto e' il costruttore.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        runs_root: Path,
        workspaces_root: Path,
        *,
        budget_usd: float | None = None,
        backends: dict[str, Backend] | None = None,
        tools_builder: Callable[[str], list] = build_default_tools,
        reporter: RunReporter | None = None,
    ):
        """Registra cio' che e' comune a tutti gli agenti costruiti.

        Args:
            registry: il listino condiviso (modelli, ruoli, prezzi).
            runs_root: directory che raccoglie i ledger; ogni incarico ne crea
                una sottodirectory propria.
            workspaces_root: directory che raccoglie i workspace; ogni agente
                ne ha uno.
            budget_usd: tetto di spesa **per agente**, valido per tutta la sua
                vita (il contabile e' unico), oppure `None` per nessun limite.
                Ogni agente ne riceve un guardiano distinto, perche' il
                guardiano ha uno stato (l'avviso morbido va emesso una volta
                sola) che non va condiviso.
            backends: mappa fornitore -> modo di raggiungerlo; `None` usa
                `BACKEND_PER_PROVIDER`. Iniettabile per poter sostituire i
                fornitori reali nei test.
            tools_builder: costruisce gli strumenti a partire dal percorso del
                workspace. Di default quelli standard, con sandbox Docker.
            reporter: chi emette il rapporto a fine incarico; `None` usa quello
                di default, che stampa.

        Raises:
            ValueError: se il tetto di spesa non e' valido. Si controlla qui e
                non alla prima `build`, cosi' un errore di configurazione
                emerge all'avvio e non a meta' di un esperimento.
        """
        BudgetGuard(budget_usd)  # solo per validare: ogni agente avra' il suo
        self.registry = registry
        self.runs_root = Path(runs_root)
        self.workspaces_root = Path(workspaces_root)
        self.budget_usd = budget_usd
        self.backends = BACKEND_PER_PROVIDER if backends is None else backends
        self.tools_builder = tools_builder
        self.reporter = reporter

    def build(self, role: str) -> BuiltAgent:
        """Costruisce un agente persistente per il ruolo dato.

        L'ordine e' voluto: prima si risolve e si controlla tutto cio' che puo'
        fallire senza lasciare tracce (ruolo, fornitore, credenziali), poi si
        crea il workspace. Un errore di configurazione non deve lasciare una
        cartella vuota in giro. I ledger non si creano qui: nascono uno per
        incarico, in `BuiltAgent.assign`.

        Args:
            role: nome del ruolo, come compare in `[roles.*]`.

        Returns:
            L'agente, senza ancora alcun incarico.

        Raises:
            RoleNotFound: se il ruolo non e' dichiarato.
            UnsupportedProvider: se il fornitore del modello non ha un gateway.
            RuntimeError: se mancano le credenziali del fornitore.
        """
        model = self.registry.model_for(role)
        provider = self.registry.models[model]["provider"]

        backend = self.backends.get(provider)
        if backend is None:
            raise UnsupportedProvider(
                f"il modello '{model}' (ruolo '{role}') appartiene al fornitore "
                f"'{provider}', che non ha un gateway di chat; "
                f"supportati: {', '.join(sorted(self.backends)) or '(nessuno)'}"
            )

        credenziali = config.credenziali_fornitore(
            provider, self.registry.providers[provider])
        client = backend.make_client(credenziali)

        agent_id = f"{role}-{uuid4().hex[:8]}"
        # Un guardiano e un contabile per agente: vedi la nota di design.
        guardiano = BudgetGuard(self.budget_usd)
        accountant = LedgerAccountant(InMemoryAccountant(self.registry))
        gateway = backend.gateway(
            client, model, accountant,
            api_model=self.registry.api_model_for(model),
            # Chiamando il fornitore direttamente, chi risponde e chi fattura
            # coincidono. Va dichiarato: il default della classe e' quello di
            # OpenAI, sbagliato per Moonshot e MiniMax che ne usano il formato.
            api_provider=provider,
            billing_provider=provider,
            budget_guard=guardiano,
        )

        # Il workspace porta l'id dell'agente, non quello di una run: vale per
        # tutta la sua vita, incarichi compresi.
        workspace = self.workspaces_root / agent_id
        agent = Agent(gateway, self.tools_builder(str(workspace)))

        def open_ledger(task: str) -> RunLedger:
            """Crea il ledger di un incarico, con la policy di budget in testa."""
            ledger = RunLedger(
                root=self.runs_root, task=task, agent_id=agent_id, role=role)
            ledger.append_event("budget_policy", guardiano.policy_details)
            return ledger

        return BuiltAgent(
            agent=agent, gateway=gateway, accountant=accountant,
            agent_id=agent_id, role=role, model=model, workspace=workspace,
            open_ledger=open_ledger, reporter=self.reporter,
        )
