"""La fabbrica costruisce agenti persistenti per ruolo, ciascuno con risorse proprie.

Nota di design (tesi):
    Si usa il `models.toml` reale del progetto, non un registro inventato: cosi'
    i test verificano anche che ruoli, fornitori e mappa dei gateway siano
    coerenti fra loro. Gli strumenti reali (sandbox Docker) sono sostituiti da
    un costruttore finto, perche' qui non interessa cio' che l'agente sa fare ma
    come viene assemblato. I client degli SDK vengono costruiti davvero con
    chiavi fittizie e poi sostituiti con client finti quando serve eseguire un
    incarico: nessun test tocca la rete.
"""

import json
from types import SimpleNamespace as NS

import pytest

from accounting import ModelRegistry, RoleNotFound
from agent_factory import (
    BACKEND_PER_PROVIDER,
    AgentDismissed,
    AgentFactory,
    UnsupportedProvider,
)
from llm_gateway import AnthropicChatGateway, ChatGatewayBase, OpenAIChatGateway
from run_reporter import RunReporter


class ReporterMuto(RunReporter):
    """Reporter che non stampa: nei test il rapporto non serve."""

    def emit(self, summary, events, ledger_path, agent_message=None) -> str:
        return ""


class ClientOpenAIFinto:
    """Client nel formato `chat.completions` che registra cio' che riceve."""

    def __init__(self, testo="ok", prompt=100, completion=50):
        self.richieste = []
        self.testo, self.prompt, self.completion = testo, prompt, completion
        self.chat = NS(completions=NS(create=self._crea))

    def _crea(self, **kwargs):
        self.richieste.append(kwargs)
        return NS(
            id=f"chat_{len(self.richieste)}",
            usage=NS(prompt_tokens=self.prompt, completion_tokens=self.completion,
                     prompt_tokens_details=None, completion_tokens_details=None),
            choices=[NS(finish_reason="stop",
                        message=NS(content=self.testo, tool_calls=None))],
        )


class ClientAnthropicFinto:
    """Client nel formato Messages di Anthropic che registra cio' che riceve."""

    def __init__(self, input_tokens=1_000_000):
        self.richieste = []
        self.input_tokens = input_tokens
        self.messages = NS(create=self._crea)

    def _crea(self, **kwargs):
        self.richieste.append(kwargs)
        return NS(
            id=f"msg_{len(self.richieste)}", stop_reason="end_turn",
            usage=NS(input_tokens=self.input_tokens, output_tokens=0,
                     cache_read_input_tokens=0, cache_creation_input_tokens=0),
            content=[NS(type="text", text="ok")],
        )


@pytest.fixture
def chiavi(monkeypatch):
    """Chiavi fittizie per i fornitori usati dai ruoli di `models.toml`."""
    monkeypatch.setenv("ORC2_ANTHROPIC_KEY", "chiave-fittizia")
    monkeypatch.setenv("ORC2_MINIMAX_KEY", "chiave-fittizia")


@pytest.fixture
def percorsi_workspace():
    """Registra i percorsi con cui la fabbrica ha chiesto gli strumenti."""
    return []


@pytest.fixture
def fabbrica(tmp_path, chiavi, percorsi_workspace):
    """Fabbrica sul registro reale, con strumenti finti e cartelle temporanee."""
    def strumenti_finti(percorso):
        percorsi_workspace.append(percorso)
        return []

    return AgentFactory(
        ModelRegistry.from_file("models.toml"),
        runs_root=tmp_path / "runs",
        workspaces_root=tmp_path / "workspaces",
        tools_builder=strumenti_finti,
        reporter=ReporterMuto(),
    )


# ── Due ruoli, due agenti diversi ─────────────────────────────────────────

def test_due_ruoli_producono_agenti_con_modelli_e_fornitori_diversi(fabbrica):
    """E' il cuore dell'instradamento statico: il ruolo decide tutto il resto.

    Il planner va su Anthropic col suo gateway; il worker su MiniMax, che parla
    il formato OpenAI. L'agente non lo sa: riceve un gateway e basta.
    """
    planner = fabbrica.build("planner")
    worker = fabbrica.build("worker")

    assert (planner.model, worker.model) == ("opus-5", "minimax-m2-7")
    assert isinstance(planner.gateway, AnthropicChatGateway)
    assert isinstance(worker.gateway, OpenAIChatGateway)
    assert planner.agent.llm is planner.gateway


def test_il_gateway_riceve_il_nome_del_fornitore_e_non_l_alias(fabbrica):
    """Il percorso diretto richiede il nome che il fornitore conosce davvero."""
    planner = fabbrica.build("planner")

    assert planner.gateway.model == "opus-5"             # chiave del progetto
    assert planner.gateway.api_model == "claude-opus-5"  # nome del fornitore


def test_il_worker_riceve_il_nome_minimax_non_l_alias(fabbrica):
    """MiniMax chiama il modello `MiniMax-M2.7`: l'alias del progetto non esiste per lui."""
    worker = fabbrica.build("worker")

    assert worker.gateway.model == "minimax-m2-7"
    assert worker.gateway.api_model == "MiniMax-M2.7"


def test_chi_risponde_e_chi_fattura_coincidono_col_fornitore(fabbrica):
    """Il default del gateway OpenAI sarebbe "openai": sbagliato per MiniMax.

    Senza dichiararlo, ogni record del worker risulterebbe fatturato da un
    fornitore che non c'entra, e il confronto fra percorsi (che e' la misura
    centrale di M2s.4) sarebbe falsato.
    """
    worker = fabbrica.build("worker")

    assert worker.gateway.api_provider == "minimax"
    assert worker.gateway.billing_provider == "minimax"


# ── L'agente e' persistente ───────────────────────────────────────────────

def test_costruire_un_agente_non_crea_alcun_ledger(fabbrica, tmp_path):
    """I ledger nascono uno per incarico, non alla nascita dell'agente."""
    costruito = fabbrica.build("worker")

    assert costruito.ledgers == []
    assert not (tmp_path / "runs").exists()


def test_ogni_incarico_ha_il_suo_ledger_chiuso_e_lo_stesso_agente(fabbrica):
    """Un incarico e' una run completa; l'agente e' uno solo.

    Il costo per task si legge nel summary di ciascun ledger — e' cio' che
    servira' alla metrica CPT-tau e al dataset del router.
    """
    worker = fabbrica.build("worker")
    worker.gateway.client = ClientOpenAIFinto()

    primo = worker.assign("primo task")
    secondo = worker.assign("secondo task")

    assert (primo.status, secondo.status) == ("completed", "completed")
    a, b = worker.ledgers
    assert a.run_id != b.run_id and a.run_dir != b.run_dir
    assert a.agent_id == b.agent_id == worker.agent_id
    assert a.role == b.role == "worker"
    for ledger in (a, b):
        sommario = json.loads((ledger.run_dir / "summary.json").read_text())
        assert sommario["status"] == "completed"
        assert sommario["usage_count"] == 1


def test_il_contabile_somma_tutta_la_vita_e_ogni_ledger_solo_il_suo_incarico(fabbrica):
    worker = fabbrica.build("worker")
    worker.gateway.client = ClientOpenAIFinto(prompt=1_000_000, completion=0)

    worker.assign("primo")
    worker.assign("secondo")

    costo_incarico = 0.24  # un milione di token di input a $0.24
    totali = [json.loads((l.run_dir / "summary.json").read_text())["total_cost"]
              for l in worker.ledgers]
    assert totali == [pytest.approx(costo_incarico)] * 2
    assert worker.accountant.total_cost == pytest.approx(2 * costo_incarico)


def test_la_conversazione_prosegue_fra_un_incarico_e_l_altro(fabbrica):
    """L'agente ricorda: il secondo incarico vede il primo e la sua risposta."""
    worker = fabbrica.build("worker")
    client = ClientOpenAIFinto(testo="fatto il primo")
    worker.gateway.client = client

    worker.assign("primo task")
    worker.assign("secondo task")

    visti = [(m["role"], m["content"]) for m in client.richieste[1]["messages"]]
    assert visti[1:] == [
        ("user", "primo task"),
        ("assistant", "fatto il primo"),
        ("user", "secondo task"),
    ]
    assert visti[0][0] == "system"


# ── Eliminare un agente ───────────────────────────────────────────────────

def test_dismiss_restituisce_il_riepilogo_della_vita_dell_agente(fabbrica):
    worker = fabbrica.build("worker")
    worker.gateway.client = ClientOpenAIFinto()
    worker.assign("primo")
    worker.assign("secondo")

    riepilogo = worker.dismiss()

    assert riepilogo["agent_id"] == worker.agent_id
    assert riepilogo["assignments"] == 2
    assert riepilogo["run_ids"] == [l.run_id for l in worker.ledgers]
    assert riepilogo["total_cost"] == worker.accountant.total_cost


def test_un_agente_eliminato_non_accetta_altri_incarichi(fabbrica, tmp_path):
    worker = fabbrica.build("worker")
    worker.dismiss()

    with pytest.raises(AgentDismissed):
        worker.assign("task")

    assert not (tmp_path / "runs").exists()  # nessun ledger creato per nulla


# ── Risorse separate per agente ───────────────────────────────────────────

def test_i_costi_finiscono_su_contabili_separati(fabbrica):
    """Un consumo del planner non deve comparire fra i costi del worker."""
    planner = fabbrica.build("planner")
    worker = fabbrica.build("worker")
    planner.gateway.client = ClientAnthropicFinto(input_tokens=1_000_000)
    worker.gateway.client = ClientOpenAIFinto(prompt=0, completion=0)

    planner.assign("task")

    assert planner.accountant.total_cost == pytest.approx(5.0)  # $5 per milione
    assert worker.accountant.total_cost == 0.0
    assert worker.ledgers == []


def test_ogni_agente_ha_un_workspace_proprio_e_disgiunto(fabbrica, percorsi_workspace):
    """Due agenti che scrivono la stessa cartella si corrompono a vicenda."""
    fabbrica.build("planner")
    fabbrica.build("worker")
    primo, secondo = percorsi_workspace

    assert primo != secondo
    assert not primo.startswith(secondo + "/") and not secondo.startswith(primo + "/")


def test_il_workspace_porta_l_id_dell_agente_e_vale_per_tutta_la_sua_vita(fabbrica):
    """Non e' legato a un incarico: l'agente lo usa finche' vive."""
    costruito = fabbrica.build("worker")

    assert costruito.workspace.name == costruito.agent_id
    assert costruito.agent_id.startswith("worker-")


def test_due_costruzioni_dello_stesso_ruolo_non_condividono_nulla(fabbrica):
    a = fabbrica.build("worker")
    b = fabbrica.build("worker")

    assert a.agent_id != b.agent_id
    assert a.workspace != b.workspace
    assert a.accountant is not b.accountant
    assert a.agent is not b.agent


# ── Il budget e' per agente ───────────────────────────────────────────────

def test_ogni_agente_riceve_un_guardiano_del_budget_distinto(tmp_path, chiavi):
    """Il guardiano ha uno stato: l'avviso morbido si emette una volta sola.

    Se due agenti ne condividessero uno, l'avviso del primo azzererebbe quello
    del secondo, e il tetto sarebbe consumato da chi non l'ha speso.
    """
    fabbrica = AgentFactory(
        ModelRegistry.from_file("models.toml"),
        runs_root=tmp_path / "runs", workspaces_root=tmp_path / "ws",
        budget_usd=0.05, tools_builder=lambda percorso: [],
    )
    a = fabbrica.build("planner")
    b = fabbrica.build("worker")

    assert a.gateway.budget_guard is not None and b.gateway.budget_guard is not None
    assert a.gateway.budget_guard is not b.gateway.budget_guard
    assert a.gateway.budget_guard.hard_limit_usd == 0.05


def test_la_policy_di_budget_e_registrata_in_ogni_ledger_all_avvio(tmp_path, chiavi):
    fabbrica = AgentFactory(
        ModelRegistry.from_file("models.toml"),
        runs_root=tmp_path / "runs", workspaces_root=tmp_path / "ws",
        budget_usd=0.05, tools_builder=lambda percorso: [], reporter=ReporterMuto(),
    )
    worker = fabbrica.build("worker")
    worker.gateway.client = ClientOpenAIFinto(prompt=1, completion=1)

    worker.assign("primo")
    worker.assign("secondo")

    for ledger in worker.ledgers:
        primo_evento = ledger.read_events()[0]
        assert primo_evento["event_type"] == "budget_policy"
        assert primo_evento["details"]["hard_limit_usd"] == 0.05


def test_il_tetto_vale_per_tutta_la_vita_dell_agente_non_per_incarico(tmp_path, chiavi):
    """Il contabile e' unico, quindi il guardiano vede la spesa di tutta la vita.

    Il primo incarico spende oltre il tetto; il secondo viene fermato prima di
    toccare la rete.
    """
    fabbrica = AgentFactory(
        ModelRegistry.from_file("models.toml"),
        runs_root=tmp_path / "runs", workspaces_root=tmp_path / "ws",
        budget_usd=0.001, tools_builder=lambda percorso: [], reporter=ReporterMuto(),
    )
    worker = fabbrica.build("worker")
    client = ClientOpenAIFinto(prompt=1000, completion=1000)  # $0.0012 a chiamata
    worker.gateway.client = client

    primo = worker.assign("primo")
    secondo = worker.assign("secondo")

    assert primo.status == "completed"
    assert secondo.status == "budget_exhausted"
    assert len(client.richieste) == 1


def test_un_budget_non_valido_fallisce_alla_creazione_della_fabbrica(tmp_path):
    """Un errore di configurazione deve emergere all'avvio, non a meta' run."""
    with pytest.raises(ValueError):
        AgentFactory(ModelRegistry.from_file("models.toml"),
                     runs_root=tmp_path / "runs", workspaces_root=tmp_path / "ws",
                     budget_usd=-1)


# ── Gli errori non lasciano tracce ────────────────────────────────────────

def test_ruolo_ignoto_e_un_errore_parlante_e_non_crea_nulla(
        fabbrica, tmp_path, percorsi_workspace):
    with pytest.raises(RoleNotFound):
        fabbrica.build("giudice")

    assert percorsi_workspace == []          # gli strumenti non sono stati costruiti
    assert not (tmp_path / "runs").exists()


def test_fornitore_senza_gateway_e_un_errore_parlante_e_non_crea_nulla(
        tmp_path, chiavi):
    """Un default silenzioso manderebbe la richiesta al gateway sbagliato."""
    costruiti = []
    fabbrica = AgentFactory(
        ModelRegistry.from_file("models.toml"),
        runs_root=tmp_path / "runs", workspaces_root=tmp_path / "ws",
        backends={}, tools_builder=lambda percorso: costruiti.append(percorso) or [],
    )

    with pytest.raises(UnsupportedProvider) as errore:
        fabbrica.build("planner")

    assert "anthropic" in str(errore.value)
    assert costruiti == []


def test_credenziali_mancanti_nominano_il_fornitore_e_non_creano_nulla(
        fabbrica, monkeypatch, percorsi_workspace):
    """La ricerca delle chiavi precede la creazione del workspace."""
    monkeypatch.delenv("ORC2_MINIMAX_KEY")

    with pytest.raises(RuntimeError) as errore:
        fabbrica.build("worker")

    assert "minimax" in str(errore.value) and "ORC2_MINIMAX_KEY" in str(errore.value)
    assert percorsi_workspace == []


# ── La mappa dei fornitori ────────────────────────────────────────────────

def test_ogni_fornitore_mappato_esiste_nel_registro():
    """Una voce nella mappa che il registro non conosce non sarebbe raggiungibile."""
    registro = ModelRegistry.from_file("models.toml")

    assert set(BACKEND_PER_PROVIDER) <= set(registro.providers)


def test_i_fornitori_in_formato_openai_condividono_il_gateway():
    """Moonshot e MiniMax differiscono per indirizzo e chiave, non per formato."""
    classi = {BACKEND_PER_PROVIDER[p].gateway for p in ("openai", "moonshot", "minimax")}

    assert classi == {OpenAIChatGateway}
    assert BACKEND_PER_PROVIDER["anthropic"].gateway is AnthropicChatGateway


def test_un_fornitore_non_conversazionale_non_e_mappato():
    """`tripo` genera asset 3D: non ha un gateway di chat e non deve averlo."""
    assert "tripo" not in BACKEND_PER_PROVIDER


def test_il_client_usa_l_indirizzo_dichiarato_nel_registro(fabbrica):
    """`base_url` viaggia dal registro al client, non e' scritto nel codice."""
    worker = fabbrica.build("worker")

    assert isinstance(worker.gateway, ChatGatewayBase)
    assert str(worker.gateway.client.base_url).startswith("https://api.minimax.io")
