"""Lo sciame minimo (R3): piano, ondate, cancello, una sola escalation, tetto di squadra.

Nota di design (tesi):
    Nessun test chiama un modello o Docker. La fabbrica e' finta e consegna
    agenti finti il cui comportamento si decide per ruolo e per prompt; il
    cancello e' una funzione iniettata che restituisce i verdetti in sequenza.
    La squadra invece e' quella vera (`Team`): il tetto e' proprio cio' che si
    vuole provare, e un finto proverebbe solo il finto.
"""

import json
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from accounting import ModelRegistry
from accounting.base import SpendReader
from agent import RunResult
from run_status import RunStatus
from budget_guard import BudgetVerdict
from gate import GateVerdict
from renderer import RenderError
from swarm import SwarmResult, planner_prompt, run_swarm, worker_prompt
from swarm_plan import parse_plan

REGISTRO = ModelRegistry.from_file("models.toml")

PROMPT = """Build a car rental site.

## Routes contract

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| GET | `/api/cars` | - | 200 | - |
| POST | `/api/bookings` | `{car_id}` | 201 | 400 |
"""


def _pezzo(id_, files, depends_on=(), routes=(), worker="worker_cheap"):
    return {"id": id_, "files": list(files), "depends_on": list(depends_on),
            "description": f"descrizione di {id_}", "routes": list(routes), "worker": worker}


PIANO = json.dumps({"style": ":root { --accent: #c33; }", "pieces": [
    _pezzo("skeleton", ["start.sh", "server.js"]),
    _pezzo("cars", ["routes/cars.js"], ["skeleton"], ["GET /api/cars"]),
    _pezzo("bookings", ["routes/bookings.js"], ["skeleton"], ["POST /api/bookings"], worker="worker"),
    _pezzo("page", ["public/index.html"], ["cars", "bookings"]),
]})


# ── Finti ─────────────────────────────────────────────────────────────────

class ContabileFinto(SpendReader):
    def __init__(self):
        self.costo, self.chiamate = 0.0, 0

    @property
    def total_cost(self) -> float:
        return self.costo

    @property
    def call_count(self) -> int:
        return self.chiamate


class AgenteFinto:
    """Si comporta come `BuiltAgent`; rispetta il tetto di squadra come il gateway vero."""

    def __init__(self, fabbrica, indice, role, workspace, team):
        self.fabbrica, self.role, self.workspace, self.team = fabbrica, role, workspace, team
        self.agent_id = f"{role}-{indice}"
        self.model = REGISTRO.model_for(role)
        self.accountant = ContabileFinto()
        self.ledgers = []
        self.prompts = []
        if team is not None:
            team.accountant.add(self.agent_id, self.accountant)

    def assign(self, task, max_iterations=None):
        self.prompts.append(task)
        self.ledgers.append(NS(run_id=f"run-{self.agent_id}-{len(self.ledgers)}"))
        with self.fabbrica.lock:
            self.fabbrica.inizi.append((self.agent_id, task, time.monotonic()))
        if self.team is not None and self.team.guard.check(self.team.accountant.total_cost) \
                is BudgetVerdict.HARD_LIMIT_REACHED:
            return RunResult(status=RunStatus.BUDGET_EXHAUSTED, iterations=0)
        esito, messaggio, costo = self.fabbrica.comportamento(self, task)
        self.accountant.costo += costo
        self.accountant.chiamate += 1
        with self.fabbrica.lock:
            self.fabbrica.fini.append((self.agent_id, time.monotonic()))
        if isinstance(esito, BaseException):
            raise esito
        return RunResult(status=RunStatus(esito), iterations=1, final_message=messaggio)


def _pezzo_del_prompt(task):
    """Il pezzo di un worker si riconosce dalla sua descrizione nel prompt."""
    if "YOUR PIECE" not in task:
        return None
    trovato = re.search(r"descrizione di (\w+)", task.split("YOUR PIECE", 1)[1])
    return trovato.group(1) if trovato else None


class FabbricaFinta:
    """Registra le `build`; il comportamento predefinito e' un piano valido e worker riusciti."""

    def __init__(self, *, piani=(PIANO,), esiti_pezzi=None, costo=0.01, budget_usd=None):
        self.registry = REGISTRO
        self.budget_usd = budget_usd
        self.piani = list(piani)
        self.esiti_pezzi = esiti_pezzi or {}
        self.costo = costo
        self.costruiti: list[AgenteFinto] = []
        self.build_args: list[dict] = []
        self.inizi, self.fini = [], []
        self.lock = threading.Lock()
        self.escalation = ("completed", "corretto", 0.05)

    def build(self, role, *, workspace=None, team=None):
        with self.lock:
            self.build_args.append({"role": role, "workspace": workspace, "team": team})
            agente = AgenteFinto(self, len(self.costruiti), role, workspace, team)
            self.costruiti.append(agente)
        return agente

    def comportamento(self, agente, task):
        if agente.role == "planner":
            planner = [a for a in self.costruiti if a.role == "planner"]
            if agente is not planner[0]:
                return self.escalation
            indice = len(agente.prompts) - 1
            return "completed", self.piani[min(indice, len(self.piani) - 1)], self.costo
        esito = self.esiti_pezzi.get(_pezzo_del_prompt(task), "completed")
        if callable(esito):
            esito = esito()
        return esito, "fatto", self.costo

    def ruoli(self):
        return [a["role"] for a in self.build_args]

    def pezzi_costruiti(self):
        return [_pezzo_del_prompt(a.prompts[0]) for a in self.costruiti if a.role != "planner" and a.prompts]


class CancelloFinto:
    def __init__(self, *verdetti):
        self.verdetti = list(verdetti) or [GateVerdict(True)]
        self.chiamate = []

    def __call__(self, workspace, out_dir):
        self.chiamate.append((Path(workspace), Path(out_dir)))
        verdetto = self.verdetti[min(len(self.chiamate) - 1, len(self.verdetti) - 1)]
        if isinstance(verdetto, BaseException):
            raise verdetto
        return verdetto


def _esegui(tmp_path, fabbrica=None, cancello=None, budget_usd=None, prompt=PROMPT, **extra):
    fabbrica = fabbrica or FabbricaFinta()
    cancello = cancello or CancelloFinto()
    ws, out = tmp_path / "ws", tmp_path / "out"
    ws.mkdir(exist_ok=True)
    esito = run_swarm(fabbrica, prompt, ws, out, budget_usd=budget_usd, gate=cancello, **extra)
    return esito, fabbrica, cancello


def _registro(esito):
    return [json.loads(r) for r in esito.log_path.read_text().splitlines() if r]


def _eventi(esito, nome):
    return [e for e in _registro(esito) if e["event"] == nome]


# ── Percorso riuscito ─────────────────────────────────────────────────────

def test_w1_piano_ondate_e_cancello_che_accetta(tmp_path):
    esito, fabbrica, cancello = _esegui(tmp_path)

    assert isinstance(esito, SwarmResult)
    assert esito.status == "completed"
    assert esito.gate == GateVerdict(True)
    assert esito.escalated is False
    assert esito.pieces == {"skeleton": "completed", "cars": "completed", "bookings": "completed",
                            "page": "completed"}
    assert fabbrica.ruoli()[0] == "planner"
    assert sorted(fabbrica.ruoli()[1:]) == ["worker", "worker_cheap", "worker_cheap", "worker_cheap"]
    assert len(cancello.chiamate) == 1


def test_w2_ogni_agente_lavora_sul_workspace_comune_nella_stessa_squadra(tmp_path):
    esito, fabbrica, _ = _esegui(tmp_path)

    assert {a["workspace"] for a in fabbrica.build_args} == {tmp_path / "ws"}
    squadre = {id(a["team"]) for a in fabbrica.build_args}
    assert len(squadre) == 1 and fabbrica.build_args[0]["team"] is not None


def test_w3_il_worker_di_ogni_pezzo_e_quello_scelto_nel_piano(tmp_path):
    _, fabbrica, _ = _esegui(tmp_path)

    per_pezzo = {_pezzo_del_prompt(a.prompts[0]): a.role for a in fabbrica.costruiti if a.role != "planner"}
    assert per_pezzo == {"skeleton": "worker_cheap", "cars": "worker_cheap", "bookings": "worker",
                         "page": "worker_cheap"}


def test_w4_un_ondata_parte_solo_quando_la_precedente_e_finita(tmp_path):
    _, fabbrica, _ = _esegui(tmp_path)

    inizio = {_pezzo_del_prompt(t): s for _, t, s in fabbrica.inizi if _pezzo_del_prompt(t)}
    fine = {_pezzo_del_prompt(a.prompts[0]): s for a in fabbrica.costruiti for i, s in fabbrica.fini
            if i == a.agent_id and a.role != "planner"}
    assert inizio["cars"] >= fine["skeleton"] and inizio["bookings"] >= fine["skeleton"]
    assert inizio["page"] >= max(fine["cars"], fine["bookings"])


def test_w5_i_pezzi_della_stessa_ondata_girano_in_parallelo(tmp_path):
    """Se cars e bookings girassero in serie, la barriera scadrebbe e i pezzi fallirebbero."""
    barriera = threading.Barrier(2, timeout=5)

    def insieme():
        barriera.wait()
        return "completed"

    fabbrica = FabbricaFinta(esiti_pezzi={"cars": insieme, "bookings": insieme})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica, max_parallel=4)

    assert esito.pieces["cars"] == esito.pieces["bookings"] == "completed"


# ── Pezzi falliti ─────────────────────────────────────────────────────────

def test_w6_un_pezzo_fallito_blocca_solo_chi_ne_dipende(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": "max_iterations"})
    esito, _, cancello = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.pieces == {"skeleton": "completed", "cars": "max_iterations", "bookings": "completed",
                            "page": "skipped"}
    assert "page" not in fabbrica.pezzi_costruiti()
    assert len(cancello.chiamate) >= 1  # il sito si consegna e si controlla comunque


def test_w7_un_eccezione_di_un_worker_e_un_pezzo_fallito_non_un_guasto_dello_sciame(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={"bookings": RuntimeError("esploso")})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.pieces["bookings"] == "unexpected_error"
    assert esito.pieces["page"] == "skipped"
    riga = [e for e in _eventi(esito, "piece") if e["piece_id"] == "bookings"][0]
    assert riga["error_type"] == "RuntimeError"


# ── Piano: rigenerazioni ──────────────────────────────────────────────────

def test_w8_un_piano_invalido_si_rigenera_con_l_errore_nello_stesso_planner(tmp_path):
    fabbrica = FabbricaFinta(piani=("niente json", '{"style": "x", "pieces": []}', PIANO))
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    planner = fabbrica.costruiti[0]
    assert planner.role == "planner" and len(planner.prompts) == 3
    assert "JSON" in planner.prompts[1]
    assert esito.status == "completed"
    assert [e["valid"] for e in _eventi(esito, "plan")] == [False, False, True]
    assert _eventi(esito, "plan")[0]["error"]


def test_w9_tre_piani_invalidi_sono_plan_failed_senza_worker_ne_cancello(tmp_path):
    fabbrica = FabbricaFinta(piani=("niente json",))
    esito, _, cancello = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.status == "plan_failed"
    assert fabbrica.ruoli() == ["planner"]
    assert len(fabbrica.costruiti[0].prompts) == 3
    assert cancello.chiamate == []
    assert esito.gate is None and esito.escalated is False


def test_w10_un_planner_fermato_dal_tetto_non_si_rigenera(tmp_path):
    fabbrica = FabbricaFinta(costo=1.0)
    fabbrica.piani = ["niente json"]
    esito, _, cancello = _esegui(tmp_path, fabbrica=fabbrica, budget_usd=0.5)

    assert esito.status == "budget_exhausted"
    assert fabbrica.ruoli() == ["planner"]
    assert cancello.chiamate == []


# ── Cancello ed escalation ────────────────────────────────────────────────

def test_w11_se_il_cancello_rifiuta_opus_corregge_una_volta_con_il_motivo(tmp_path):
    cancello = CancelloFinto(GateVerdict(False, "/ risponde con stato 404 a 375 px"), GateVerdict(True))
    esito, fabbrica, _ = _esegui(tmp_path, cancello=cancello)

    planner = [a for a in fabbrica.costruiti if a.role == "planner"]
    assert len(planner) == 2, "l'escalation e' un agente Opus nuovo, non la conversazione del planner"
    assert "/ risponde con stato 404 a 375 px" in planner[1].prompts[0]
    assert esito.escalated is True
    assert esito.gate == GateVerdict(True)
    assert [e["phase"] for e in _eventi(esito, "gate")] == ["initial", "after_escalation"]


def test_w12_l_escalation_e_una_sola_anche_se_il_cancello_rifiuta_ancora(tmp_path):
    cancello = CancelloFinto(GateVerdict(False, "non partito"), GateVerdict(False, "ancora no"))
    esito, fabbrica, _ = _esegui(tmp_path, cancello=cancello)

    assert fabbrica.ruoli().count("planner") == 2
    assert len(cancello.chiamate) == 2
    assert esito.gate == GateVerdict(False, "ancora no")
    assert esito.status == "completed"


def test_w13_se_il_cancello_accetta_non_c_e_escalation(tmp_path):
    esito, fabbrica, _ = _esegui(tmp_path)

    assert fabbrica.ruoli().count("planner") == 1
    assert _eventi(esito, "escalation") == []


def test_w14_le_osservazioni_del_cancello_non_finiscono_dove_scrive_la_valutazione(tmp_path):
    cancello = CancelloFinto(GateVerdict(False, "x"), GateVerdict(True))
    _esegui(tmp_path, cancello=cancello)

    cartelle = [out for _, out in cancello.chiamate]
    assert len(set(cartelle)) == 2
    for cartella in cartelle:
        assert cartella.is_relative_to(tmp_path / "out" / "sciame")


def test_w15_un_guasto_del_renderer_si_registra_e_non_fa_scattare_l_escalation(tmp_path):
    esito, fabbrica, _ = _esegui(tmp_path, cancello=CancelloFinto(RenderError("Docker spento")))

    assert esito.gate is None and esito.escalated is False
    assert fabbrica.ruoli().count("planner") == 1
    assert "Docker spento" in _eventi(esito, "gate")[0]["error"]


# ── Tetto di squadra ──────────────────────────────────────────────────────

def test_w16_al_tetto_nessun_pezzo_parte_e_si_consegna_il_lavoro_fatto(tmp_path):
    """Planner e scheletro spendono 0,02 $ con un tetto di 0,015: la seconda ondata non parte."""
    cancello = CancelloFinto(GateVerdict(False, "incompleto"))
    esito, fabbrica, _ = _esegui(tmp_path, cancello=cancello, budget_usd=0.015)

    assert esito.status == "budget_exhausted"
    assert fabbrica.pezzi_costruiti() == ["skeleton"]
    assert {k: v for k, v in esito.pieces.items() if k != "skeleton"} == {
        "cars": "not_started", "bookings": "not_started", "page": "not_started"}
    assert len(cancello.chiamate) == 1, "il cancello registra comunque il verdetto sul lavoro consegnato"
    assert esito.escalated is False, "al tetto l'escalation non parte"
    assert len(_eventi(esito, "budget_stop")) == 1


def test_w17_il_costo_dello_sciame_e_quello_della_squadra(tmp_path):
    esito, fabbrica, _ = _esegui(tmp_path)

    assert esito.total_cost == pytest.approx(0.01 * 5)
    assert sorted(esito.run_ids) == sorted(l.run_id for a in fabbrica.costruiti for l in a.ledgers)


def test_w18_un_tetto_non_valido_e_un_errore_prima_di_costruire_agenti(tmp_path):
    fabbrica = FabbricaFinta()
    with pytest.raises(ValueError):
        _esegui(tmp_path, fabbrica=fabbrica, budget_usd=0)
    assert fabbrica.costruiti == []


# ── Registro ──────────────────────────────────────────────────────────────

def test_w19_il_registro_ha_ruolo_pezzo_modello_e_costo_per_ogni_pezzo(tmp_path):
    esito, fabbrica, _ = _esegui(tmp_path)

    righe = {e["piece_id"]: e for e in _eventi(esito, "piece")}
    assert set(righe) == {"skeleton", "cars", "bookings", "page"}
    assert righe["bookings"]["role"] == "worker"
    assert righe["bookings"]["model"] == "kimi-k3-1-pro"
    assert righe["cars"]["model"] == "deepseek-v4-1-flash"
    assert (righe["skeleton"]["wave"], righe["cars"]["wave"], righe["page"]["wave"]) == (0, 1, 2)
    for riga in righe.values():
        assert riga["agent_id"] and riga["run_id"] and riga["status"] == "completed"
        assert riga["cost"] == pytest.approx(0.01)
    fine = _eventi(esito, "end")
    assert len(fine) == 1 and fine[0]["total_cost"] == pytest.approx(esito.total_cost)
    assert fine[0]["status"] == "completed" and fine[0]["gate"] == {"accepted": True, "reason": None}
    assert esito.log_path.parent == tmp_path / "out" / "sciame"


# ── Prompt e invisibilita' della valutazione ──────────────────────────────

def test_w20_il_planner_vede_compito_rotte_prezzi_e_dato_di_design_arena():
    testo = planner_prompt(PROMPT, REGISTRO, ("GET /api/cars", "POST /api/bookings"))

    assert PROMPT.strip() in testo
    assert "GET /api/cars" in testo and "POST /api/bookings" in testo
    for prezzo in ("0.15", "0.60", "2.00", "10.00"):
        assert prezzo in testo
    assert "worker_cheap" in testo and "worker" in testo
    assert "Design Arena" in testo


def test_w21_il_worker_vede_compito_stile_il_suo_pezzo_e_i_file_dei_vicini():
    piano = parse_plan(PIANO, routes=("GET /api/cars", "POST /api/bookings"), workers=("worker", "worker_cheap"))
    cars = piano.pieces[1]

    testo = worker_prompt(PROMPT, piano, cars)

    assert PROMPT.strip() in testo
    assert ":root { --accent: #c33; }" in testo
    assert "descrizione di cars" in testo and "routes/cars.js" in testo and "GET /api/cars" in testo
    assert "routes/bookings.js" in testo and "server.js" in testo
    assert "YOUR PIECE" in testo


def test_w22_lo_sciame_non_tocca_mai_la_valutazione():
    """Come per il cancello (R2.6): i moduli dello sciame non nominano script o risultati riservati."""
    for modulo in ("swarm.py", "swarm_plan.py"):
        sorgente = Path(modulo).read_text()
        for vietato in ("valutazione", "r1_valutazione", "riservato", "webcampaign", "evaluate_site"):
            assert vietato not in sorgente, (modulo, vietato)


def test_w23_un_compito_senza_contratto_si_pianifica_senza_rotte(tmp_path):
    piano = json.dumps({"style": "x", "pieces": [_pezzo("s", ["start.sh", "index.html"])]})
    esito, _, _ = _esegui(tmp_path, fabbrica=FabbricaFinta(piani=(piano,)), prompt="Build a static page.\n")

    assert esito.status == "completed" and esito.pieces == {"s": "completed"}
