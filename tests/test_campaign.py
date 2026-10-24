"""La campagna lancia task in serie e ne calcola `f` e la quota di output.

Nota di design (tesi):
    Nessun test tocca rete o Docker. La fabbrica e' sostituita da una finta che
    consegna agenti finti; la shell (setup e verifica dei task) e' una funzione
    iniettata. Il solo test che esegue shell vera usa la `bash` locale, per
    provare che il comando di verifica di ogni task e' corretto: se `verify`
    fosse sbagliato, `f` misurerebbe l'errore del test e non quello del modello.
"""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from accounting import ModelRegistry
from agent import AgentFailure, RunResult
import campaign
from campaign import CampaignError, Task, load_tasks, report, run_campaign
from task_model import Verification, VerificationError

TASKS_M2S4A = Path("campaigns/m2s4a.toml")


# ── Finti ─────────────────────────────────────────────────────────────────

class AgenteFinto:
    """Agente costruito dalla fabbrica finta; registra l'ordine degli eventi."""

    def __init__(self, indice, workspace, eventi, esito, costo):
        self.agent_id = f"worker-{indice}"
        self.model = "minimax-m3"
        self.workspace = workspace
        self.accountant = NS(total_cost=costo)
        self.ledgers = []
        self._eventi, self._esito, self._costo = eventi, esito, costo

    def assign(self, task, max_iterations=None):
        self._eventi.append(("assign", self.agent_id))
        self.ledgers.append(NS(run_id=f"run-{self.agent_id}", run_dir=Path("x")))
        if isinstance(self._esito, BaseException):
            raise self._esito
        return RunResult(status=self._esito, iterations=1)


class FabbricaFinta:
    """Registra le `build` e consegna un agente nuovo a ogni chiamata."""

    def __init__(self, tmp_path, esiti=None, costo=0.01, build_falliti=()):
        self.tmp_path, self.costo = tmp_path, costo
        self.build_falliti = set(build_falliti)   # indici di chiamata che sollevano
        self.esiti = list(esiti or [])
        self.eventi = []
        self.costruiti = []
        self.build_riusciti_o_no = []

    def build(self, role):
        indice = len(self.costruiti) + len(self.build_riusciti_o_no)
        self.build_riusciti_o_no.append(indice)
        if indice in self.build_falliti:
            raise RuntimeError("chiave mancante")
        indice = len(self.costruiti)
        workspace = self.tmp_path / "ws" / f"agente-{indice}"
        workspace.mkdir(parents=True)
        esito = self.esiti[indice] if indice < len(self.esiti) else "completed"
        agente = AgenteFinto(indice, workspace, self.eventi, esito, self.costo)
        self.costruiti.append(agente)
        self.eventi.append(("build", agente.agent_id))
        return agente


def shell_che_registra(eventi, esiti_verify=None, setup_exit=0, solleva_in_verify=None,
                       solleva_in_setup=None):
    """Shell finta: registra i comandi; `verify` risponde secondo la lista data.

    `setup_exit` e' l'exit code del setup; `solleva_in_*` e' un'eccezione da
    sollevare, per simulare un Docker che si ferma o un timeout.
    """
    esiti = list(esiti_verify or [])

    def shell(workspace, comando):
        if comando.startswith("VERIFY"):
            eventi.append(("verify", workspace.name))
            if solleva_in_verify:
                raise solleva_in_verify
            return 0 if (esiti.pop(0) if esiti else True) else 1
        eventi.append(("setup", workspace.name))
        if solleva_in_setup:
            raise solleva_in_setup
        return setup_exit

    return shell


def due_task():
    return [
        Task(id="t1", prompt="p1", setup="SETUP 1", verify="VERIFY 1"),
        Task(id="t2", prompt="p2", setup=None, verify="VERIFY 2"),
    ]


def righe(percorso):
    return [json.loads(r) for r in percorso.read_text().splitlines()]


# ── A3: un agente e un workspace nuovi per ogni run; ordine degli eventi ──

def test_ogni_run_ha_agente_e_workspace_nuovi_e_l_ordine_e_setup_assign_verify(tmp_path):
    fabbrica = FabbricaFinta(tmp_path)
    shell = shell_che_registra(fabbrica.eventi)

    run_campaign(fabbrica, due_task(), role="worker", repetitions=2,
                 campaign_id="c1", campaigns_dir=tmp_path / "campagne", shell=shell)

    assert len({a.agent_id for a in fabbrica.costruiti}) == 4
    assert len({a.workspace for a in fabbrica.costruiti}) == 4
    # Prima run (task t1, rep 1): costruzione, poi setup, poi incarico, poi verifica.
    tipi = [tipo for tipo, _ in fabbrica.eventi[:4]]
    assert tipi == ["build", "setup", "assign", "verify"]


# ── A4: successo = completed E verificato ─────────────────────────────────

@pytest.mark.parametrize("esito, verifica, atteso", [
    ("completed", True, True),
    ("completed", False, False),   # il «fatto!» senza lavoro fatto
    ("budget_exhausted", True, False),
    ("budget_exhausted", False, False),
])
def test_successo_richiede_completed_e_verifica_superata(tmp_path, esito, verifica, atteso):
    fabbrica = FabbricaFinta(tmp_path, esiti=[esito])
    shell = shell_che_registra(fabbrica.eventi, esiti_verify=[verifica])

    righe_manifesto = run_campaign(
        fabbrica, due_task()[:1], role="worker", repetitions=1,
        campaign_id="c1", campaigns_dir=tmp_path / "campagne", shell=shell)

    assert righe_manifesto[0]["status"] == esito
    assert righe_manifesto[0]["verified"] is verifica
    assert righe_manifesto[0]["success"] is atteso


def test_un_guasto_inatteso_e_una_riga_e_la_campagna_prosegue(tmp_path):
    guasto = AgentFailure(2, RuntimeError("boom"))
    fabbrica = FabbricaFinta(tmp_path, esiti=[guasto, "completed"])
    shell = shell_che_registra(fabbrica.eventi)

    manifesto = run_campaign(fabbrica, due_task(), role="worker", repetitions=1,
                             campaign_id="c1", campaigns_dir=tmp_path / "campagne", shell=shell)

    assert [r["status"] for r in manifesto] == ["unexpected_error", "completed"]
    assert [r["success"] for r in manifesto] == [False, True]


def test_il_manifesto_su_disco_ha_una_riga_per_run_con_i_campi_promessi(tmp_path):
    fabbrica = FabbricaFinta(tmp_path, costo=0.0123)
    run_campaign(fabbrica, due_task(), role="worker", repetitions=2,
                 campaign_id="c1", campaigns_dir=tmp_path / "campagne",
                 shell=shell_che_registra(fabbrica.eventi))

    contenuto = righe(tmp_path / "campagne" / "c1.jsonl")
    assert len(contenuto) == 4
    assert {"task_id", "rep", "run_id", "agent_id", "model", "status", "verified",
            "success", "total_cost"} <= set(contenuto[0])
    assert [(r["task_id"], r["rep"]) for r in contenuto] == [
        ("t1", 1), ("t1", 2), ("t2", 1), ("t2", 2)]
    assert contenuto[0]["total_cost"] == pytest.approx(0.0123)


# ── A5: tetto di campagna ─────────────────────────────────────────────────

def test_il_tetto_di_campagna_ferma_il_ciclo_prima_della_run_successiva(tmp_path):
    fabbrica = FabbricaFinta(tmp_path, costo=0.30)   # ogni run costa 0.30
    shell = shell_che_registra(fabbrica.eventi)

    manifesto = run_campaign(
        fabbrica, due_task(), role="worker", repetitions=3, max_total_usd=0.50,
        campaign_id="c1", campaigns_dir=tmp_path / "campagne", shell=shell)

    # 0.30 < 0.50: la 2a run parte; 0.60 >= 0.50: la 3a non parte.
    assert len(fabbrica.costruiti) == 2
    assert len([r for r in manifesto if r.get("task_id")]) == 2
    assert manifesto[-1]["stopped"] == "max_total_usd"


# ── A6: input non valido → errore prima di creare qualunque cartella ──────

def test_file_task_valido_viene_letto(tmp_path):
    percorso = tmp_path / "t.toml"
    percorso.write_text('[[task]]\nid="a"\nprompt="p"\nverify="true"\n')
    assert load_tasks(percorso) == [Task(id="a", prompt="p", setup=None, verify="true")]


@pytest.mark.parametrize("testo", [
    '[[task]]\nid="a"\nprompt="p"\n',                                         # senza verify
    '[[task]]\nid="a"\nprompt="p"\nverify="x"\n[[task]]\nid="a"\nprompt="q"\nverify="y"\n',  # id doppio
    '[[task]]\nid="a"\nverify="x"\n',                                          # senza prompt
    "questo non e' toml [[[",                                                  # malformato
    "",                                                                        # nessun task
])
def test_file_task_non_valido_da_un_errore_parlante(tmp_path, testo):
    percorso = tmp_path / "t.toml"
    percorso.write_text(testo)
    with pytest.raises(CampaignError):
        load_tasks(percorso)


@pytest.mark.parametrize("ripetizioni", [0, -1])
def test_ripetizioni_non_valide_non_creano_ne_agenti_ne_cartelle(tmp_path, ripetizioni):
    fabbrica = FabbricaFinta(tmp_path)
    with pytest.raises(CampaignError):
        run_campaign(fabbrica, due_task(), role="worker", repetitions=ripetizioni,
                     campaign_id="c1", campaigns_dir=tmp_path / "campagne",
                     shell=shell_che_registra(fabbrica.eventi))
    assert fabbrica.costruiti == []
    assert not (tmp_path / "campagne" / "c.jsonl").exists()
    assert not (tmp_path / "campagne").exists()


# ── I 10 task veri: la verifica e' affidabile ─────────────────────────────

def _bash(cartella, comando):
    return subprocess.run(["bash", "-c", comando], cwd=cartella,
                          capture_output=True).returncode


def test_il_file_dei_task_ha_dieci_task_validi():
    tasks = load_tasks(TASKS_M2S4A)
    assert len(tasks) == 10
    assert len({t.id for t in tasks}) == 10


def _riferimenti():
    """Soluzioni di controllo lette dal file, che le tiene a parte dal modello."""
    import tomllib
    return {t["id"]: t["reference"] for t in tomllib.loads(TASKS_M2S4A.read_text())["task"]}


def _id_dei_task():
    import tomllib
    return [t["id"] for t in tomllib.loads(TASKS_M2S4A.read_text())["task"]]


@pytest.mark.parametrize("task_id", _id_dei_task())
def test_verify_fallisce_senza_lavoro_e_passa_con_la_soluzione_giusta(tmp_path, task_id):
    task = next(t for t in load_tasks(TASKS_M2S4A) if t.id == task_id)
    riferimento = _riferimenti()[task_id]

    solo_setup = tmp_path / "vuoto"
    solo_setup.mkdir()
    if task.setup:
        assert _bash(solo_setup, task.setup) == 0
    assert _bash(solo_setup, task.verify) != 0, "verify passa anche senza fare nulla"

    risolto = tmp_path / "risolto"
    risolto.mkdir()
    if task.setup:
        assert _bash(risolto, task.setup) == 0
    assert _bash(risolto, riferimento) == 0
    assert _bash(risolto, task.verify) == 0, "verify rifiuta la soluzione giusta"


# ── A7: il report ─────────────────────────────────────────────────────────

def _scrivi_run(runs_root, run_id, quantita):
    cartella = runs_root / run_id
    cartella.mkdir(parents=True)
    (cartella / "summary.json").write_text(json.dumps({"run_id": run_id}))
    with open(cartella / "usage.jsonl", "w") as f:
        f.write(json.dumps({"record": {"model": "minimax-m3", "quantities": quantita}}) + "\n")


def _manifesto(percorso, esiti):
    with open(percorso, "w") as f:
        for i, (task, rep, ok) in enumerate(esiti):
            f.write(json.dumps({
                "task_id": task, "rep": rep, "run_id": f"r{i}", "model": "minimax-m3",
                "status": "completed" if ok else "unexpected_error",
                "verified": ok, "success": ok, "total_cost": 0.0}) + "\n")


def test_il_report_calcola_f_e_la_quota_di_output_sul_listino(tmp_path):
    """Listino minimax-m3: input 0.30, output 1.20, cache letta 0.06 $/M.

    Per run: 1000 input -> 0.0003; 2000 cache -> 0.00012; 500 output -> 0.0006.
    Totale 0.00102. Quota output in costo = 0.0006/0.00102 = 0.5882;
    in token = 500/3500 = 0.1429. Quattro run: 3 successi, 1 fallimento.
    """
    runs = tmp_path / "runs"
    quantita = {"input_tokens": 1000, "cached_input_tokens": 2000, "output_tokens": 500}
    for i in range(4):
        _scrivi_run(runs, f"r{i}", quantita)
    manifesto = tmp_path / "c1.jsonl"
    _manifesto(manifesto, [("t1", 1, True), ("t1", 2, False), ("t2", 1, True), ("t2", 2, True)])

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.runs == 4
    assert esito.failure_rate == pytest.approx(0.25)
    assert esito.failure_rate_by_task == {"t1": pytest.approx(0.5), "t2": pytest.approx(0.0)}
    assert esito.total_cost == pytest.approx(4 * 0.00102)
    assert esito.output_cost_share == pytest.approx(0.0006 / 0.00102)
    assert esito.output_token_share == pytest.approx(500 / 3500)
    assert esito.unpriced_records == 0


def test_un_consumo_senza_prezzo_si_conta_a_parte_e_non_sparisce(tmp_path):
    runs = tmp_path / "runs"
    _scrivi_run(runs, "r0", {"input_tokens": 1000, "unita_inventata": 7})
    manifesto = tmp_path / "c1.jsonl"
    _manifesto(manifesto, [("t1", 1, True)])

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.unpriced_records == 1
    assert esito.total_cost == pytest.approx(0.0003)


# ── Casi limite aggiunti dopo un secondo controllo del codice (ott 2026) ──

def _esegui(tmp_path, fabbrica, shell, ripetizioni=1, tasks=None, **extra):
    return run_campaign(fabbrica, tasks or due_task(), role="worker",
                        repetitions=ripetizioni, campaign_id="c1",
                        campaigns_dir=tmp_path / "campagne", shell=shell, **extra)


def test_r1_un_build_che_fallisce_e_una_riga_e_la_campagna_prosegue(tmp_path):
    fabbrica = FabbricaFinta(tmp_path, build_falliti={0})
    shell = shell_che_registra(fabbrica.eventi)

    manifesto = _esegui(tmp_path, fabbrica, shell)

    assert [r["status"] for r in manifesto] == ["build_failed", "completed"]
    assert manifesto[0]["error_type"] == "RuntimeError"
    assert manifesto[0]["success"] is False


@pytest.mark.parametrize("errore", [subprocess.TimeoutExpired("docker", 60), FileNotFoundError("docker")])
def test_r1_un_setup_che_solleva_e_una_riga_e_la_campagna_prosegue(tmp_path, errore):
    fabbrica = FabbricaFinta(tmp_path)
    # Il setup solleva solo per il primo task (l'unico che ne ha uno).
    shell = shell_che_registra(fabbrica.eventi, solleva_in_setup=errore)

    manifesto = _esegui(tmp_path, fabbrica, shell)

    assert manifesto[0]["status"] == "setup_failed"
    assert manifesto[0]["error_type"] == type(errore).__name__
    assert manifesto[1]["status"] == "completed"   # il secondo task non ha setup


def test_setup_con_exit_diverso_da_zero_e_setup_failed_e_non_interpella_l_agente(tmp_path):
    fabbrica = FabbricaFinta(tmp_path)
    shell = shell_che_registra(fabbrica.eventi, setup_exit=1)

    manifesto = _esegui(tmp_path, fabbrica, shell)

    assert manifesto[0]["status"] == "setup_failed"
    assert ("assign", "worker-0") not in fabbrica.eventi


@pytest.mark.parametrize("errore", [subprocess.TimeoutExpired("docker", 60), FileNotFoundError("docker")])
def test_r2_se_verify_solleva_la_run_resta_nel_manifesto_col_suo_costo(tmp_path, errore):
    fabbrica = FabbricaFinta(tmp_path, costo=0.05)
    shell = shell_che_registra(fabbrica.eventi, solleva_in_verify=errore)

    manifesto = _esegui(tmp_path, fabbrica, shell, tasks=due_task()[1:])

    assert manifesto[0]["verified"] is False
    assert manifesto[0]["success"] is False
    assert manifesto[0]["total_cost"] == pytest.approx(0.05)   # la spesa non sparisce
    assert len(righe(tmp_path / "campagne" / "c1.jsonl")) == 1


def test_r3_il_report_non_conta_i_guasti_della_campagna_come_fallimenti_del_modello(tmp_path):
    runs = tmp_path / "runs"
    _scrivi_run(runs, "r0", {"input_tokens": 1000})
    manifesto = tmp_path / "c1.jsonl"
    with open(manifesto, "w") as f:
        f.write(json.dumps({"task_id": "t1", "rep": 1, "run_id": "r0", "status": "completed",
                            "success": True, "total_cost": 0.0}) + "\n")
        f.write(json.dumps({"task_id": "t1", "rep": 2, "run_id": None, "status": "setup_failed",
                            "success": False, "total_cost": 0.0}) + "\n")
        f.write(json.dumps({"task_id": "t1", "rep": 3, "run_id": None, "status": "build_failed",
                            "success": False, "total_cost": 0.0}) + "\n")

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.runs == 1
    assert esito.failure_rate == pytest.approx(0.0)
    assert esito.excluded_runs == 2


def test_r4_un_campaign_id_gia_usato_e_un_errore_prima_di_qualunque_effetto(tmp_path):
    fabbrica = FabbricaFinta(tmp_path)
    shell = shell_che_registra(fabbrica.eventi)
    _esegui(tmp_path, fabbrica, shell, tasks=due_task()[1:])
    prima = (tmp_path / "campagne" / "c1.jsonl").read_text()
    costruiti_prima = len(fabbrica.costruiti)

    with pytest.raises(CampaignError, match="c1"):
        _esegui(tmp_path, fabbrica, shell, tasks=due_task()[1:])

    assert (tmp_path / "campagne" / "c1.jsonl").read_text() == prima
    assert len(fabbrica.costruiti) == costruiti_prima


@pytest.mark.parametrize("testo", [
    'task = "x"\n',                                              # non e' una lista di tabelle
    '[task]\nid="a"\nprompt="p"\nverify="x"\n',               # tabella singola
    '[[task]]\nid=1\nprompt="p"\nverify="x"\n',               # id non stringa
    '[[task]]\nid="a"\nprompt="p"\nverify=true\n',            # verify non stringa
    '[[task]]\nid="a"\nprompt="p"\nverify="x"\nsetup=3\n',   # setup non stringa
])
def test_r5_forme_inattese_nel_file_task_sono_campaign_error(tmp_path, testo):
    percorso = tmp_path / "t.toml"
    percorso.write_text(testo)
    with pytest.raises(CampaignError):
        load_tasks(percorso)


def test_r6_la_cli_su_una_campagna_inesistente_risponde_con_errore_e_codice_2(tmp_path, capsys):
    assert campaign.main(["report", "campagna-che-non-esiste"]) == 2
    assert "errore" in capsys.readouterr().err


def test_r7_una_run_senza_usage_si_conta_a_parte_e_unpriced_conta_i_record(tmp_path):
    runs = tmp_path / "runs"
    _scrivi_run(runs, "r0", {"input_tokens": 1000, "unita_a": 1, "unita_b": 2})
    manifesto = tmp_path / "c1.jsonl"
    _manifesto(manifesto, [("t1", 1, True), ("t1", 2, True)])   # r1 non ha usage.jsonl

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.runs_without_usage == 1
    assert esito.unpriced_records == 1      # un record, anche se con due unita' senza prezzo


def test_a3_rafforzato_verify_gira_nel_workspace_del_proprio_agente_in_ogni_run(tmp_path):
    fabbrica = FabbricaFinta(tmp_path)
    shell = shell_che_registra(fabbrica.eventi)

    _esegui(tmp_path, fabbrica, shell, ripetizioni=2)

    costruiti = [n for tipo, n in fabbrica.eventi if tipo == "build"]
    verificati = [n for tipo, n in fabbrica.eventi if tipo == "verify"]
    # Il workspace di `worker-i` si chiama `agente-i`: stessa posizione = stessa run.
    assert [n.replace("worker-", "agente-") for n in costruiti] == verificati


# ── Task con file e ripristino dei test (polyglot) ────────────────────────

def test_c1_i_file_del_task_sono_nel_workspace_prima_dell_incarico(tmp_path):
    visti = {}

    class AgenteCheLeggeIlWorkspace(AgenteFinto):
        def assign(self, task, max_iterations=None):
            visti["alla_assegnazione"] = sorted(
                str(p.relative_to(self.workspace)) for p in self.workspace.rglob("*") if p.is_file())
            return super().assign(task, max_iterations)

    class Fabbrica(FabbricaFinta):
        def build(self, role):
            agente = super().build(role)
            agente.__class__ = AgenteCheLeggeIlWorkspace
            return agente

    fabbrica = Fabbrica(tmp_path)
    task = Task(id="t", prompt="p", verify="VERIFY",
                files={"e.py": "pass\n", "sotto/dir/e_test.py": "# test\n"})

    run_campaign(fabbrica, [task], role="worker", repetitions=1, campaign_id="c1",
                 campaigns_dir=tmp_path / "campagne", shell=shell_che_registra(fabbrica.eventi))

    assert visti["alla_assegnazione"] == ["e.py", "sotto/dir/e_test.py"]


def test_c2_i_test_modificati_dall_agente_sono_ripristinati_prima_della_verifica(tmp_path):
    letti = {}

    class AgenteCheBara(AgenteFinto):
        def assign(self, task, max_iterations=None):
            (self.workspace / "e_test.py").write_text("def test_ok(): assert True  # TRUCCATO\n")
            (self.workspace / "e.py").write_text("# la soluzione dell'agente\n")
            return super().assign(task, max_iterations)

    class Fabbrica(FabbricaFinta):
        def build(self, role):
            agente = super().build(role)
            agente.__class__ = AgenteCheBara
            return agente

    def shell(workspace, comando):
        if comando.startswith("VERIFY"):
            letti["test"] = (workspace / "e_test.py").read_text()
            letti["soluzione"] = (workspace / "e.py").read_text()
        return 0

    fabbrica = Fabbrica(tmp_path)
    task = Task(id="t", prompt="p", verify="VERIFY",
                files={"e.py": "pass\n", "e_test.py": "# originale\n"},
                restore={"e_test.py": "# originale\n"})

    run_campaign(fabbrica, [task], role="worker", repetitions=1, campaign_id="c1",
                 campaigns_dir=tmp_path / "campagne", shell=shell)

    assert letti["test"] == "# originale\n"                         # il trucco non conta
    assert letti["soluzione"] == "# la soluzione dell'agente\n"      # il lavoro dell'agente resta


def test_c3_un_task_senza_file_si_comporta_come_prima(tmp_path):
    fabbrica = FabbricaFinta(tmp_path)

    manifesto = run_campaign(fabbrica, due_task(), role="worker", repetitions=1,
                             campaign_id="c1", campaigns_dir=tmp_path / "campagne",
                             shell=shell_che_registra(fabbrica.eventi))

    assert [r["status"] for r in manifesto] == ["completed", "completed"]
    assert not any(fabbrica.costruiti[0].workspace.iterdir())


def test_c4_da_main_una_cartella_di_esercizi_diventa_l_elenco_dei_task(tmp_path, monkeypatch):
    import campaign as modulo
    from tests.test_polyglot import _scrivi_esercizio

    radice = tmp_path / "practice"
    _scrivi_esercizio(radice, "uno")
    _scrivi_esercizio(radice, "due")
    viste = {}
    monkeypatch.setattr(modulo, "run_campaign", lambda factory, tasks, **kw: viste.update(tasks=tasks, **kw) or [])
    monkeypatch.setattr(modulo, "AgentFactory", lambda *a, **kw: NS())

    codice = modulo.main(
        ["run", "--tasks", str(radice), "--only", "uno", "--budget-usd", "0.01",
         "--max-total-usd", "1.0", "--campaign-id", "x"], dotenv_path=tmp_path / ".env")

    assert codice == 0
    assert [t.id for t in viste["tasks"]] == ["uno"]


def test_c4b_un_nome_inesistente_con_only_e_un_errore_e_non_parte_nulla(tmp_path, monkeypatch, capsys):
    import campaign as modulo
    from tests.test_polyglot import _scrivi_esercizio

    radice = tmp_path / "practice"
    _scrivi_esercizio(radice, "uno")
    monkeypatch.setattr(modulo, "run_campaign", lambda *a, **kw: pytest.fail("non doveva partire"))

    codice = modulo.main(
        ["run", "--tasks", str(radice), "--only", "inventato", "--budget-usd", "0.01",
         "--max-total-usd", "1.0", "--campaign-id", "x"], dotenv_path=tmp_path / ".env")

    assert codice == 2
    assert "inventato" in capsys.readouterr().err


# ── Casi limite aggiunti dopo un terzo controllo del codice (ott 2026) ────

def test_r3_il_ripristino_non_segue_un_link_simbolico_fuori_dal_workspace(tmp_path):
    from campaign import _scrivi_file
    fuori = tmp_path / "fuori.txt"
    fuori.write_text("ORIGINALE FUORI DAL WORKSPACE")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "e_test.py").symlink_to("../fuori.txt")

    with pytest.raises(CampaignError, match="link"):
        _scrivi_file(ws, {"e_test.py": "# ripristinato"})

    assert fuori.read_text() == "ORIGINALE FUORI DAL WORKSPACE"


def test_r3b_nemmeno_una_cartella_che_e_un_link_fuori_dal_workspace(tmp_path):
    from campaign import _scrivi_file
    fuori = tmp_path / "fuori"
    fuori.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "sotto").symlink_to("../fuori")

    with pytest.raises(CampaignError):
        _scrivi_file(ws, {"sotto/e_test.py": "# ripristinato"})

    assert list(fuori.iterdir()) == []


def test_r3c_in_campagna_un_tentativo_di_link_e_una_verifica_fallita_con_traccia(tmp_path):
    fuori = tmp_path / "fuori.txt"
    fuori.write_text("ORIGINALE")

    class AgenteCheFaUnLink(AgenteFinto):
        def assign(self, task, max_iterations=None):
            (self.workspace / "e_test.py").unlink()
            (self.workspace / "e_test.py").symlink_to(fuori)
            return super().assign(task, max_iterations)

    class Fabbrica(FabbricaFinta):
        def build(self, role):
            agente = super().build(role)
            agente.__class__ = AgenteCheFaUnLink
            return agente

    fabbrica = Fabbrica(tmp_path)
    task = Task(id="t", prompt="p", verify="VERIFY", files={"e_test.py": "# originale\n"},
                restore={"e_test.py": "# originale\n"})

    manifesto = run_campaign(fabbrica, [task], role="worker", repetitions=1, campaign_id="c1",
                             campaigns_dir=tmp_path / "campagne",
                             shell=shell_che_registra(fabbrica.eventi))

    assert fuori.read_text() == "ORIGINALE"                  # il file fuori non e' stato toccato
    assert manifesto[0]["verified"] is False and manifesto[0]["success"] is False
    assert manifesto[0]["error_type"] == "CampaignError"      # e la riga lo dice


# ── Da riga di comando il modulo si chiama `__main__`: gli errori devono reggere ──

import subprocess
import sys


def _cli(*argomenti, cwd="."):
    return subprocess.run([sys.executable, "campaign.py", *argomenti], cwd=cwd,
                          capture_output=True, text=True, timeout=60)


def test_r2_task_model_e_l_unica_casa_di_task_e_campaign_error():
    import campaign
    import polyglot
    import task_model

    assert campaign.CampaignError is task_model.CampaignError
    assert polyglot.PolyglotError.__mro__[1] is task_model.CampaignError
    assert campaign.Task is task_model.Task


def test_r2b_da_riga_di_comando_un_esercizio_inesistente_da_errore_e_codice_2(tmp_path):
    from tests.test_polyglot import _scrivi_esercizio
    radice = tmp_path / "practice"
    _scrivi_esercizio(radice, "uno")

    r = _cli("run", "--tasks", str(radice), "--only", "inventato", "--budget-usd", "0.01",
             "--max-total-usd", "0.1", "--campaign-id", "prova-r2b")

    assert r.returncode == 2, r.stderr[-400:]
    assert r.stderr.startswith("errore:") or "\nerrore:" in r.stderr
    assert "Traceback" not in r.stderr


def test_r2c_da_riga_di_comando_fetch_su_cartella_esistente_da_errore_e_codice_2(tmp_path):
    r = _cli("fetch-polyglot", "--dest", str(tmp_path))          # tmp_path esiste gia'

    assert r.returncode == 2, r.stderr[-400:]
    assert "esiste" in r.stderr and "Traceback" not in r.stderr


# ── Report: fallimenti per causa e request_id duplicati (M2s, chiusura) ────
#
# Nota di design (tesi):
#    `f` da solo mescola cose diverse: un modello che sbaglia la soluzione, uno che non chiude
#    entro le 30 iterazioni, uno che esaurisce il tetto di spesa. E la cache di risposte del vecchio
#    proxy faceva comparire lo stesso `request_id` in piu' run: ora deve risultare zero.

def _run_con_request_id(runs_root, run_id, request_ids):
    cartella = runs_root / run_id
    cartella.mkdir(parents=True)
    with open(cartella / "usage.jsonl", "w") as f:
        for rid in request_ids:
            f.write(json.dumps({"record": {
                "model": "minimax-m3", "quantities": {"input_tokens": 10}, "request_id": rid}}) + "\n")


def _manifesto_con_stati(percorso, righe):
    """`righe`: (run_id, status, verified). `success` = completed e verificata, come in campagna."""
    with open(percorso, "w") as f:
        for i, (run_id, status, verified) in enumerate(righe):
            f.write(json.dumps({
                "task_id": f"t{i}", "rep": 1, "run_id": run_id, "model": "minimax-m3",
                "status": status, "verified": verified,
                "success": status == "completed" and verified, "total_cost": 0.0}) + "\n")


def test_y1_i_fallimenti_si_contano_per_causa_e_i_guasti_della_campagna_restano_fuori(tmp_path):
    runs = tmp_path / "runs"
    righe = [("r0", "completed", True),             # successo: non e' un fallimento
             ("r1", "max_iterations", False),
             ("r2", "max_iterations", False),
             ("r3", "budget_exhausted", False),
             ("r4", "unexpected_error", False),
             ("r5", "completed", False),            # dichiara di aver finito ma la verifica non passa
             ("r6", "setup_failed", False)]         # guasto della campagna: fuori da `f`
    for run_id, _, _ in righe:
        _run_con_request_id(runs, run_id, [f"id-{run_id}"])
    manifesto = tmp_path / "c.jsonl"
    _manifesto_con_stati(manifesto, righe)

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.failures_by_cause == {
        "max_iterations": 2, "budget_exhausted": 1, "unexpected_error": 1, "verification_failed": 1}
    assert esito.runs == 6 and esito.excluded_runs == 1
    assert sum(esito.failures_by_cause.values()) == round(esito.failure_rate * esito.runs)


def test_y2_senza_fallimenti_le_cause_sono_vuote(tmp_path):
    runs = tmp_path / "runs"
    _run_con_request_id(runs, "r0", ["a"])
    manifesto = tmp_path / "c.jsonl"
    _manifesto_con_stati(manifesto, [("r0", "completed", True)])

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.failures_by_cause == {}


def test_y3_un_request_id_in_piu_run_e_segnalato(tmp_path):
    runs = tmp_path / "runs"
    _run_con_request_id(runs, "r0", ["gen-a", "gen-b"])
    _run_con_request_id(runs, "r1", ["gen-b", "gen-c"])      # gen-b ripetuto fra due run
    _run_con_request_id(runs, "r2", ["gen-d", "gen-d"])      # ripetuto anche dentro la stessa run
    manifesto = tmp_path / "c.jsonl"
    _manifesto_con_stati(manifesto, [("r0", "completed", True), ("r1", "completed", True),
                                     ("r2", "completed", True)])

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.duplicate_request_ids == 2                    # gen-b e gen-d


def test_y4_request_id_tutti_distinti_o_assenti_non_sono_duplicati(tmp_path):
    runs = tmp_path / "runs"
    _run_con_request_id(runs, "r0", ["gen-a", None, None])    # l'assenza non e' un duplicato
    _run_con_request_id(runs, "r1", ["gen-b"])
    manifesto = tmp_path / "c.jsonl"
    _manifesto_con_stati(manifesto, [("r0", "completed", True), ("r1", "completed", True)])

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.duplicate_request_ids == 0


def test_y5_la_riga_di_comando_stampa_cause_e_duplicati(tmp_path, monkeypatch, capsys):
    import shutil
    shutil.copy("models.toml", tmp_path / "models.toml")
    runs = tmp_path / "runs"
    (runs / "campaigns").mkdir(parents=True)
    _run_con_request_id(runs, "r0", ["gen-a"])
    _run_con_request_id(runs, "r1", ["gen-a"])
    _manifesto_con_stati(runs / "campaigns" / "x.jsonl",
                         [("r0", "max_iterations", False), ("r1", "completed", True)])
    monkeypatch.setattr(campaign, "PROJECT_ROOT", tmp_path)

    codice = campaign.main(["report", "x"])

    uscita = capsys.readouterr().out
    assert codice == 0
    assert "fallimenti per causa" in uscita and "max_iterations: 1" in uscita
    assert "request_id duplicati: 1" in uscita


# ── Rilievi della revisione: manifesto senza `status`, consumi non prezzabili ─
#
# Nota di design (tesi):
#    Una chiamata di cui il listino non conosce un'unita' (es. i token scritti in cache di Kimi) e'
#    gia' stata pagata, ma finisce nel ledger solo come EVENTO `unpriced_usage`, non come record.
#    Senza il costo riportato nell'evento, quella spesa sparirebbe sia dal confronto
#    calcolato/riportato sia dal controllo dei `request_id`.

def _scrivi_eventi(runs_root, run_id, eventi):
    cartella = runs_root / run_id
    cartella.mkdir(parents=True, exist_ok=True)
    with open(cartella / "events.jsonl", "w") as f:
        for i, dettagli in enumerate(eventi, 1):
            f.write(json.dumps({"schema_version": 3, "event_type": "unpriced_usage",
                                "run_id": run_id, "sequence": i, "details": dettagli}) + "\n")


def test_y6_una_riga_del_manifesto_senza_status_non_fa_cadere_il_report(tmp_path):
    runs = tmp_path / "runs"
    manifesto = tmp_path / "c.jsonl"
    with open(manifesto, "w") as f:
        f.write(json.dumps({"task_id": "t0", "rep": 1, "run_id": "r0", "success": False}) + "\n")

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.failures_by_cause == {"unknown": 1}


def test_z1_le_chiamate_non_prezzabili_hanno_il_loro_costo_riportato_nel_report(tmp_path):
    runs = tmp_path / "runs"
    _run_con_request_id(runs, "r0", ["gen-a"])
    # r0 ha anche una chiamata riportata e prezzata; r1 solo una non prezzabile
    with open(runs / "r0" / "usage.jsonl", "w") as f:
        f.write(json.dumps({"record": {"model": "minimax-m3", "quantities": {"input_tokens": 10},
                                       "request_id": "gen-a", "reported_cost": 0.25}}) + "\n")
    _scrivi_eventi(runs, "r1", [{"model": "kimi-k3", "request_id": "gen-u", "reason": "UnitNotFound",
                                 "quantities": {"cache_write_tokens": 100}, "reported_cost": 0.5,
                                 "served_by": "Moonshot AI"}])
    manifesto = tmp_path / "c.jsonl"
    _manifesto_con_stati(manifesto, [("r0", "completed", True), ("r1", "completed", True)])

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.unpriced_calls == 1
    assert esito.reported_cost == pytest.approx(0.75)      # 0.25 prezzata + 0.50 non prezzabile
    assert esito.reported_records == 2


def test_z2_un_request_id_ripetuto_fra_un_record_e_un_evento_non_prezzabile_e_un_duplicato(tmp_path):
    runs = tmp_path / "runs"
    _run_con_request_id(runs, "r0", ["gen-x"])
    _scrivi_eventi(runs, "r1", [{"model": "kimi-k3", "request_id": "gen-x", "reason": "UnitNotFound",
                                 "quantities": {}, "reported_cost": None}])
    manifesto = tmp_path / "c.jsonl"
    _manifesto_con_stati(manifesto, [("r0", "completed", True), ("r1", "completed", True)])

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.duplicate_request_ids == 1


def test_z3_senza_eventi_non_prezzabili_nulla_cambia(tmp_path):
    runs = tmp_path / "runs"
    _run_con_request_id(runs, "r0", ["gen-a"])
    manifesto = tmp_path / "c.jsonl"
    _manifesto_con_stati(manifesto, [("r0", "completed", True)])

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.unpriced_calls == 0 and esito.reported_cost is None


def test_z4_la_riga_di_comando_stampa_le_chiamate_non_prezzabili(tmp_path, monkeypatch, capsys):
    import shutil
    shutil.copy("models.toml", tmp_path / "models.toml")
    runs = tmp_path / "runs"
    (runs / "campaigns").mkdir(parents=True)
    _run_con_request_id(runs, "r0", ["gen-a"])
    _scrivi_eventi(runs, "r1", [{"model": "kimi-k3", "request_id": "gen-u", "reason": "UnitNotFound",
                                 "quantities": {}, "reported_cost": 0.5}])
    _manifesto_con_stati(runs / "campaigns" / "x.jsonl",
                         [("r0", "completed", True), ("r1", "completed", True)])
    monkeypatch.setattr(campaign, "PROJECT_ROOT", tmp_path)

    campaign.main(["report", "x"])

    assert "chiamate non prezzabili: 1" in capsys.readouterr().out


# ── M3.1: piu' run insieme ────────────────────────────────────────────────

import threading  # noqa: E402
import time  # noqa: E402

from run_status import RunStatus  # noqa: E402

# Il fixture della suite sostituisce `time.sleep`: le pause che fanno parte della prova usano questa.
dormi = time.sleep


class AgenteConcorrente:
    """Un agente che, durante l'incarico, scrive nel proprio workspace e misura la concorrenza."""

    def __init__(self, indice, workspace, costo, fabbrica):
        self.agent_id = f"conc-{indice}"
        self.model = "minimax-m3"
        self.workspace = workspace
        self.accountant = NS(total_cost=costo)
        self.ledgers = []
        self._fabbrica = fabbrica

    def assign(self, task, max_iterations=None):
        f = self._fabbrica
        self.ledgers.append(NS(run_id=f"run-{self.agent_id}", run_dir=Path("x")))
        with f.lock:
            f.attivi += 1
            f.massimo = max(f.massimo, f.attivi)
        try:
            if f.barriera is not None:
                f.barriera.wait(timeout=5)
            dormi(f.ritardi.get(task, 0.0))
            if task in f.solleva_per:
                raise f.solleva_per[task]
            (self.workspace / "marcatore.txt").write_text(self.agent_id)
        finally:
            with f.lock:
                f.attivi -= 1
        return RunResult(status=RunStatus.COMPLETED, iterations=1)


class FabbricaConcorrente:
    """Come `FabbricaFinta`, ma sicura fra thread: due `build` insieme non si pestano."""

    def __init__(self, tmp_path, costo=0.0, costi=None, barriera=None, ritardi=None, solleva_per=None):
        self.tmp_path, self.costo, self.costi = tmp_path, costo, costi
        self.barriera, self.ritardi, self.solleva_per = barriera, ritardi or {}, solleva_per or {}
        self.lock = threading.Lock()
        self.costruiti, self.attivi, self.massimo = [], 0, 0

    def build(self, role):
        with self.lock:
            indice = len(self.costruiti)
            workspace = self.tmp_path / "ws" / f"conc-{indice}"
            workspace.mkdir(parents=True)
            costo = self.costi[indice] if self.costi else self.costo
            agente = AgenteConcorrente(indice, workspace, costo, self)
            self.costruiti.append(agente)
        return agente


def _task(n):
    return [Task(id=f"t{i}", prompt=f"p{i}", setup=None, verify=f"VERIFY {i}") for i in range(n)]


def _lancia(fabbrica, tasks, tmp_path, **kwargs):
    kwargs.setdefault("repetitions", 1)
    return run_campaign(fabbrica, tasks, role="worker", campaign_id="c", campaigns_dir=tmp_path / "campagne",
                        shell=shell_che_registra([]), **kwargs)


def test_con_piu_operai_le_run_partono_insieme_e_ognuna_ha_il_suo_workspace(tmp_path):
    """La barriera si supera solo se le tre run sono in corso nello stesso momento."""
    fabbrica = FabbricaConcorrente(tmp_path, barriera=threading.Barrier(3))

    manifesto = _lancia(fabbrica, _task(3), tmp_path, workers=3)

    assert [r["success"] for r in manifesto] == [True, True, True]
    assert len({a.workspace for a in fabbrica.costruiti}) == 3
    for agente in fabbrica.costruiti:
        # Isolamento: nel workspace di ognuno c'e' solo il file scritto da lui.
        assert [p.name for p in agente.workspace.iterdir()] == ["marcatore.txt"]
        assert (agente.workspace / "marcatore.txt").read_text() == agente.agent_id


def test_il_manifesto_resta_jsonl_valido_con_molte_run_concorrenti(tmp_path):
    fabbrica = FabbricaConcorrente(tmp_path)

    _lancia(fabbrica, _task(12), tmp_path, workers=6)

    scritte = righe(tmp_path / "campagne" / "c.jsonl")      # ogni riga si legge come JSON
    assert len(scritte) == 12
    assert len({r["agent_id"] for r in scritte}) == 12


def test_la_somma_dei_costi_delle_righe_e_la_somma_dei_contabili(tmp_path):
    fabbrica = FabbricaConcorrente(tmp_path, costi=[0.01 * (i + 1) for i in range(8)])

    manifesto = _lancia(fabbrica, _task(8), tmp_path, workers=4)

    assert sum(r["total_cost"] for r in manifesto) == pytest.approx(
        sum(a.accountant.total_cost for a in fabbrica.costruiti))
    # Attribuzione: ogni riga porta il costo del *suo* agente.
    per_agente = {a.agent_id: a.accountant.total_cost for a in fabbrica.costruiti}
    assert all(r["total_cost"] == per_agente[r["agent_id"]] for r in manifesto)


def test_le_righe_tornano_nell_ordine_dei_task_anche_se_le_run_finiscono_al_contrario(tmp_path):
    fabbrica = FabbricaConcorrente(tmp_path, ritardi={"p0": 0.2, "p1": 0.0})

    manifesto = _lancia(fabbrica, _task(2), tmp_path, repetitions=2, workers=4)

    assert [(r["task_id"], r["rep"]) for r in manifesto] == [("t0", 1), ("t0", 2), ("t1", 1), ("t1", 2)]


def test_un_errore_in_una_run_concorrente_non_ferma_le_altre(tmp_path):
    fabbrica = FabbricaConcorrente(tmp_path, solleva_per={"p1": RuntimeError("guasto")})

    manifesto = _lancia(fabbrica, _task(4), tmp_path, workers=3)

    assert [r["status"] for r in manifesto] == [
        RunStatus.COMPLETED, RunStatus.UNEXPECTED_ERROR, RunStatus.COMPLETED, RunStatus.COMPLETED]
    assert manifesto[1]["error_type"] == "RuntimeError"


# -- Il tetto di spesa con piu' run in volo -------------------------------------

def test_il_tetto_conta_anche_le_run_in_volo_con_la_prenotazione_del_tetto_per_run(tmp_path):
    """Tetto 0,05 e 0,02 prenotati per run: si conta anche la run che parte, quindi ne partono 2
    (0,02 e 0,04 <= 0,05); una terza porterebbe la prenotazione a 0,06. Prima ne partivano 3
    (si contavano solo quelle gia' in volo) e lo sforamento poteva arrivare a un tetto per run."""
    fabbrica = FabbricaConcorrente(tmp_path, ritardi={f"p{i}": 0.05 for i in range(6)})

    manifesto = _lancia(fabbrica, _task(6), tmp_path, workers=5,
                        max_total_usd=0.05, reserve_per_run_usd=0.02)

    assert fabbrica.massimo == 2                 # mai piu' di due insieme, anche con cinque operai
    assert len(manifesto) == 6                   # ma alla fine le run costano 0 e partono tutte


def test_il_tetto_ferma_le_nuove_partenze_e_aspetta_le_run_in_corso(tmp_path):
    fabbrica = FabbricaConcorrente(tmp_path, costo=0.03, ritardi={"p0": 0.05})

    manifesto = _lancia(fabbrica, _task(1), tmp_path, repetitions=6, workers=2,
                        max_total_usd=0.05, reserve_per_run_usd=0.01)

    assert 2 <= len(fabbrica.costruiti) <= 3     # il tetto ferma le partenze quando la spesa lo supera
    assert manifesto[-1]["stopped"] == "max_total_usd"
    assert all("task_id" in r for r in manifesto[:-1])     # ogni run partita ha la sua riga


def test_la_spesa_prenotata_non_supera_mai_il_tetto_totale(tmp_path):
    """Con il tetto pari a una sola prenotazione parte una run alla volta."""
    fabbrica = FabbricaConcorrente(tmp_path, ritardi={f"p{i}": 0.03 for i in range(4)})

    _lancia(fabbrica, _task(4), tmp_path, workers=4, max_total_usd=0.02, reserve_per_run_usd=0.02)

    assert fabbrica.massimo == 1


def test_con_piu_operai_e_un_tetto_totale_serve_il_tetto_per_run(tmp_path):
    fabbrica = FabbricaConcorrente(tmp_path)

    with pytest.raises(CampaignError, match="reserve_per_run_usd"):
        _lancia(fabbrica, _task(2), tmp_path, workers=2, max_total_usd=1.0)

    assert fabbrica.costruiti == []
    assert not (tmp_path / "campagne" / "c.jsonl").exists()
    assert not (tmp_path / "campagne").exists()


@pytest.mark.parametrize("n", [0, -2])
def test_un_numero_di_operai_non_valido_e_un_errore_prima_di_ogni_effetto(tmp_path, n):
    fabbrica = FabbricaConcorrente(tmp_path)

    with pytest.raises(CampaignError, match="workers"):
        _lancia(fabbrica, _task(2), tmp_path, workers=n)

    assert fabbrica.costruiti == [] and not (tmp_path / "campagne").exists()


# -- Riga di comando ---------------------------------------------------------

def test_la_riga_di_comando_ha_workers_con_default_uno():
    parser = campaign.build_parser()
    base = ["run", "--budget-usd", "1", "--max-total-usd", "2"]

    assert parser.parse_args(base).workers == 1
    assert parser.parse_args(base + ["--workers", "4"]).workers == 4


def test_da_main_workers_e_il_tetto_per_run_arrivano_alla_campagna(tmp_path, monkeypatch):
    import campaign as modulo
    from tests.test_polyglot import _scrivi_esercizio

    radice = tmp_path / "practice"
    _scrivi_esercizio(radice, "uno")
    viste = {}
    monkeypatch.setattr(modulo, "run_campaign", lambda factory, tasks, **kw: viste.update(**kw) or [])
    monkeypatch.setattr(modulo, "AgentFactory", lambda *a, **kw: NS())

    codice = modulo.main(
        ["run", "--tasks", str(radice), "--budget-usd", "0.01", "--max-total-usd", "1.0",
         "--workers", "3", "--campaign-id", "x"], dotenv_path=tmp_path / ".env")

    assert codice == 0
    assert viste["workers"] == 3 and viste["reserve_per_run_usd"] == 0.01


def test_da_main_un_numero_di_operai_non_valido_da_errore_e_codice_2(tmp_path, monkeypatch, capsys):
    import campaign as modulo
    from tests.test_polyglot import _scrivi_esercizio

    radice = tmp_path / "practice"
    _scrivi_esercizio(radice, "uno")
    monkeypatch.setattr(modulo, "AgentFactory", lambda *a, **kw: NS())

    codice = modulo.main(
        ["run", "--tasks", str(radice), "--budget-usd", "0.01", "--max-total-usd", "1.0",
         "--workers", "0"], dotenv_path=tmp_path / ".env")

    assert codice == 2 and "workers" in capsys.readouterr().err


def test_un_tetto_per_run_piu_alto_del_totale_e_un_errore_prima_di_creare_il_manifesto(tmp_path):
    """Ogni run prenota il proprio tetto: non ne partirebbe nessuna, e senza errore non si capirebbe."""
    fabbrica = FabbricaConcorrente(tmp_path)

    with pytest.raises(CampaignError):
        _lancia(fabbrica, _task(2), tmp_path, workers=1, max_total_usd=0.01, reserve_per_run_usd=0.02)

    assert fabbrica.costruiti == []
    assert not (tmp_path / "campagne" / "c.jsonl").exists()


# ── R1.5: verificatori, valutazione.json e guasti della valutazione ────────

class VerificatoreFinto:
    """Verificatore che registra dove gli si chiede di scrivere e risponde come detto."""

    def __init__(self, esito=None, solleva=None):
        self.esito = esito or Verification(verified=True, summary={"evaluation": {"funziona": 80.0}})
        self.solleva = solleva
        self.cartelle = []

    def __call__(self, workspace, out_dir, shell):
        self.cartelle.append(out_dir)
        if self.solleva:
            raise self.solleva
        return self.esito


def test_r15_1_il_verificatore_riceve_una_cartella_per_run_e_il_riassunto_va_nel_manifesto(tmp_path):
    fabbrica = FabbricaFinta(tmp_path)
    verificatore = VerificatoreFinto()
    task = Task(id="842", prompt="p", verify=verificatore)

    manifesto = _esegui(tmp_path, fabbrica, shell_che_registra(fabbrica.eventi), ripetizioni=2, tasks=[task])

    assert verificatore.cartelle == [tmp_path / "campagne" / "c1" / "842-1", tmp_path / "campagne" / "c1" / "842-2"]
    assert all(r["success"] and r["evaluation"] == {"funziona": 80.0} for r in manifesto)


def test_r15_2_un_guasto_della_valutazione_si_annota_e_non_e_un_fallimento_del_sito(tmp_path):
    fabbrica = FabbricaFinta(tmp_path, costo=0.05)
    task = Task(id="842", prompt="p", verify=VerificatoreFinto(solleva=VerificationError("eval.json illeggibile")))

    manifesto = _esegui(tmp_path, fabbrica, shell_che_registra(fabbrica.eventi), tasks=[task])

    assert manifesto[0]["evaluation_failed"] is True
    assert manifesto[0]["verified"] is False and manifesto[0]["success"] is False
    assert manifesto[0]["error_type"] == "VerificationError"
    assert manifesto[0]["total_cost"] == pytest.approx(0.05)


def test_r15_3_un_comando_shell_non_aggiunge_campi_alla_riga(tmp_path):
    fabbrica = FabbricaFinta(tmp_path)

    manifesto = _esegui(tmp_path, fabbrica, shell_che_registra(fabbrica.eventi), tasks=due_task()[1:])

    assert "evaluation" not in manifesto[0] and "evaluation_failed" not in manifesto[0]


def test_r15_4_il_report_tiene_i_guasti_della_valutazione_fuori_da_f(tmp_path):
    runs = tmp_path / "runs"
    _scrivi_run(runs, "r0", {"input_tokens": 1000})
    manifesto = tmp_path / "c1.jsonl"
    with open(manifesto, "w") as f:
        f.write(json.dumps({"task_id": "t1", "rep": 1, "run_id": "r0", "status": "completed",
                            "success": True, "total_cost": 0.0}) + "\n")
        f.write(json.dumps({"task_id": "t1", "rep": 2, "run_id": None, "status": "completed",
                            "success": False, "evaluation_failed": True, "total_cost": 0.0}) + "\n")

    esito = report(manifesto, runs, ModelRegistry.from_file("models.toml"))

    assert esito.runs == 1
    assert esito.failure_rate == pytest.approx(0.0)
    assert esito.excluded_runs == 1
