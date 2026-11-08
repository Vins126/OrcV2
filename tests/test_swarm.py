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
from swarm import SwarmResult, escalation_prompt, planner_prompt, run_swarm, worker_prompt
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


FORME = {"GET /api/cars": '200 [{"id": number, "model": string}]',
         "POST /api/bookings": '201 {"id": number}; 400 {"error": string}'}

PIANO = json.dumps({"style": ":root { --accent: #c33; }", "contract": FORME, "pieces": [
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

    def build(self, role, *, workspace=None, team=None, required_skills=()):
        with self.lock:
            self.build_args.append({"role": role, "workspace": workspace, "team": team,
                                    "required_skills": required_skills})
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
    # La build vera gira in Docker: nei test si inietta una finta che non fa nulla (MS-6).
    extra.setdefault("build_site", lambda _ws: None)
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
    """Cambio di contratto (S4, task 7): prima qui c'era `max_iterations`, che ora non blocca piu'."""
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": "loop_detected"})
    esito, _, cancello = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.pieces == {"skeleton": "completed", "cars": "loop_detected", "bookings": "completed",
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


# ── H3 (task 7): il piano valido si salva accanto al registro ─────────────

def test_h3_il_piano_valido_si_salva_in_sciame(tmp_path):
    esito, _, _ = _esegui(tmp_path)

    piano = json.loads((esito.log_path.parent / "plan.json").read_text())
    assert [p["id"] for p in piano["pieces"]] == ["skeleton", "cars", "bookings", "page"]
    assert "style" in piano


# ── S1 (task 7): il worker costoso solo dove serve ────────────────────────

def test_s1_il_planner_parte_dal_worker_economico():
    testo = planner_prompt(PROMPT, REGISTRO, ("GET /api/cars", "POST /api/bookings"))

    assert "Default to worker_cheap" in testo
    assert "front-end stuff" not in testo, "la frase che spingeva Kimi su tutta l'interfaccia"
    assert "Design Arena" in testo


# ── S2 (task 7): la correzione parte anche con pezzi non completati ───────

def _correttori(fabbrica):
    return [a for a in fabbrica.costruiti if a.role == "planner"][1:]


def test_s2_un_pezzo_non_completato_fa_partire_la_correzione_anche_se_il_cancello_accetta(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": "max_iterations"})
    esito, _, cancello = _esegui(tmp_path, fabbrica=fabbrica)

    correttori = _correttori(fabbrica)
    assert len(correttori) == 1 and esito.escalated is True
    assert "cars" in correttori[0].prompts[0] and "max_iterations" in correttori[0].prompts[0]
    assert [e["phase"] for e in _eventi(esito, "gate")] == ["initial", "after_escalation"]
    assert _eventi(esito, "escalation")[0]["incomplete"] == {"cars": "max_iterations"}
    assert len(cancello.chiamate) == 2


def test_s2_pezzi_caduti_e_saltati_sono_tutti_nella_correzione(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={"bookings": RuntimeError("esploso")})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.escalated is True
    assert _eventi(esito, "escalation")[0]["incomplete"] == {"bookings": "unexpected_error", "page": "skipped"}
    testo = _correttori(fabbrica)[0].prompts[0]
    assert "routes/bookings.js" in testo and "public/index.html" in testo


def test_s2_tutti_completati_e_cancello_che_accetta_nessuna_correzione(tmp_path):
    esito, fabbrica, _ = _esegui(tmp_path)

    assert _correttori(fabbrica) == [] and esito.escalated is False


def test_s2_la_correzione_e_una_sola_anche_con_rifiuto_e_pezzi_incompleti(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": "max_iterations"})
    cancello = CancelloFinto(GateVerdict(False, "non parte"), GateVerdict(False, "ancora no"))
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica, cancello=cancello)

    assert len(_correttori(fabbrica)) == 1
    testo = _correttori(fabbrica)[0].prompts[0]
    assert "non parte" in testo and "cars" in testo
    assert _eventi(esito, "escalation")[0]["incomplete"] == {"cars": "max_iterations"}


def test_s2_con_il_cancello_guasto_i_pezzi_incompleti_bastano_per_correggere(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": "max_iterations"})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica, cancello=CancelloFinto(RenderError("Docker spento")))

    assert esito.escalated is True and esito.gate is None


def test_s2_la_correzione_dopo_un_rifiuto_registra_un_elenco_vuoto(tmp_path):
    cancello = CancelloFinto(GateVerdict(False, "404"), GateVerdict(True))
    esito, _, _ = _esegui(tmp_path, cancello=cancello)

    assert _eventi(esito, "escalation")[0]["incomplete"] == {}


def test_s2_il_prompt_di_correzione_nomina_solo_i_problemi_che_ci_sono():
    piano = parse_plan(PIANO, routes=("GET /api/cars", "POST /api/bookings"), workers=("worker", "worker_cheap"))

    solo_pezzi = escalation_prompt(PROMPT, piano, None, {"cars": "max_iterations"})
    assert "GATE REJECTION" not in solo_pezzi
    assert "INCOMPLETE PIECES" in solo_pezzi and "cars: max_iterations" in solo_pezzi
    assert "routes/cars.js" in solo_pezzi
    assert "temporary" in solo_pezzi, "chiede di togliere codice e file provvisori lasciati dai worker"

    solo_cancello = escalation_prompt(PROMPT, piano, "404", {})
    assert "GATE REJECTION" in solo_cancello and "404" in solo_cancello
    assert "INCOMPLETE PIECES" not in solo_cancello


# ── S3 (task 7): regola nel prompt del worker ─────────────────────────────

def test_s3_il_worker_non_deve_nascondere_gli_altri_ne_lasciare_file_provvisori():
    piano = parse_plan(PIANO, routes=("GET /api/cars", "POST /api/bookings"), workers=("worker", "worker_cheap"))
    testo = worker_prompt(PROMPT, piano, piano.pieces[3])

    assert "Never hide, disable or restyle other pieces" in testo
    assert "Do not leave backup, preview or temporary files" in testo


# ── S4 (task 7): il limite di iterazioni non blocca chi dipende ───────────

def test_s4_un_pezzo_fermato_dal_limite_di_iterazioni_non_blocca_chi_ne_dipende(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": "max_iterations"})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.pieces["cars"] == "max_iterations"
    assert esito.pieces["page"] == "completed"
    assert "page" in fabbrica.pezzi_costruiti()


@pytest.mark.parametrize("stato", ["unexpected_error", "loop_detected", "output_truncated", "provider_error"])
def test_s4_gli_altri_esiti_bloccano_ancora(tmp_path, stato):
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": RuntimeError("x") if stato == "unexpected_error" else stato})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.pieces["page"] == "skipped"


# ── S5 (task 7): forma delle risposte nei prompt e nel piano salvato ──────

def test_s5_il_planner_chiede_la_forma_delle_risposte():
    testo = planner_prompt(PROMPT, REGISTRO, ("GET /api/cars", "POST /api/bookings"))

    assert '"contract"' in testo
    assert "response shape" in testo


def test_s5_ogni_worker_vede_la_forma_di_tutte_le_rotte():
    piano = parse_plan(PIANO, routes=("GET /api/cars", "POST /api/bookings"), workers=("worker", "worker_cheap"))
    testo = worker_prompt(PROMPT, piano, piano.pieces[3])  # page, che non possiede rotte

    assert "ROUTE CONTRACT" in testo
    for rotta, forma in FORME.items():
        assert f"{rotta}: {forma}" in testo


def test_s5_il_piano_salvato_contiene_il_contratto(tmp_path):
    esito, _, _ = _esegui(tmp_path)

    piano = json.loads((esito.log_path.parent / "plan.json").read_text())
    assert piano["contract"] == FORME


# ── S3 (task 7, P31-D1 (b)): controllo dei file a fine ondata ─────────────
#
# A fine ondata si confronta il workspace con quello d'inizio ondata. Si segnalano
# i file di pezzi che non stavano girando e i file provvisori senza proprietario;
# nessun pezzo si blocca, la segnalazione fa partire la correzione di S2.

def _scrive(tmp_path, *scritture, cancella=()):
    """Comportamento di un worker finto che tocca il workspace e poi riesce."""
    def azione():
        for percorso, testo in scritture:
            file = tmp_path / "ws" / percorso
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(testo)
        for percorso in cancella:
            (tmp_path / "ws" / percorso).unlink()
        return "completed"
    return azione


def test_f1_un_file_di_un_pezzo_di_un_ondata_precedente_si_segnala_e_si_corregge(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={
        "skeleton": _scrive(tmp_path, ("server.js", "base")),
        "cars": _scrive(tmp_path, ("server.js", "toccato da cars"))})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert set(esito.pieces.values()) == {"completed"}, "nessun pezzo si blocca"
    assert esito.escalated is True
    controlli = _eventi(esito, "file_check")
    assert [c["wave"] for c in controlli] == [0, 1, 2]
    assert controlli[1]["foreign"] == {"server.js": "skeleton"} and controlli[1]["temporary"] == []
    assert _eventi(esito, "escalation")[0]["file_issues"] == {"server.js": "changed, owned by skeleton"}
    testo = _correttori(fabbrica)[0].prompts[0]
    assert "FILE ISSUES" in testo and "server.js: changed, owned by skeleton" in testo


def test_f11_i_segnaposto_dello_scheletro_per_pezzi_futuri_non_si_segnalano(tmp_path):
    # Prova di C su 000058 (7 nov): lo scheletro crea file vuoti dei pezzi successivi perche' la build
    # parta; il proprietario non ha ancora lavorato e li riscrive, quindi nessun danno da correggere.
    fabbrica = FabbricaFinta(esiti_pezzi={
        "skeleton": _scrive(tmp_path, ("server.js", "base"), ("routes/cars.js", "// segnaposto"),
                            ("public/index.html", "<!-- segnaposto -->"))})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert [c["foreign"] for c in _eventi(esito, "file_check")] == [{}, {}, {}]
    assert esito.escalated is False


def test_f12_toccare_il_file_di_un_pezzo_di_un_ondata_successiva_non_si_segnala(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": _scrive(tmp_path, ("public/index.html", "anticipato"))})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert _eventi(esito, "file_check")[1]["foreign"] == {}
    assert esito.escalated is False


def test_f13_un_segnaposto_riscritto_da_un_pezzo_estraneo_dopo_il_proprietario_si_segnala(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={
        "skeleton": _scrive(tmp_path, ("routes/cars.js", "// segnaposto")),
        "cars": _scrive(tmp_path, ("routes/cars.js", "vero")),
        "page": _scrive(tmp_path, ("routes/cars.js", "rovinato"))})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert [c["foreign"] for c in _eventi(esito, "file_check")] == [{}, {}, {"routes/cars.js": "cars"}]
    assert esito.escalated is True


def test_f2_cancellare_il_file_di_un_altro_pezzo_si_segnala(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={
        "skeleton": _scrive(tmp_path, ("server.js", "base")),
        "page": _scrive(tmp_path, cancella=["server.js"])})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert _eventi(esito, "file_check")[2]["foreign"] == {"server.js": "skeleton"}
    assert esito.escalated is True


@pytest.mark.parametrize("provvisorio", ["routes/cars.js.bak", "public/goals.css.preview", "tmp-check.js",
                                         "notes.tmp", "server.js.orig", "app.old", "index.html~"])
def test_f3_un_file_provvisorio_senza_proprietario_si_segnala(tmp_path, provvisorio):
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": _scrive(tmp_path, (provvisorio, "x"))})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert _eventi(esito, "file_check")[1]["temporary"] == [provvisorio]
    assert _eventi(esito, "escalation")[0]["file_issues"] == {provvisorio: "temporary file"}


def test_f4_un_file_nuovo_non_provvisorio_e_ammesso(tmp_path):
    """Con React un worker crea componenti di supporto che il piano non elenca."""
    fabbrica = FabbricaFinta(esiti_pezzi={"page": _scrive(tmp_path, ("src/components/CarCard.jsx", "x"))})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.escalated is False
    assert all(c["foreign"] == {} and c["temporary"] == [] for c in _eventi(esito, "file_check"))


@pytest.mark.parametrize("prodotto", ["node_modules/pkg/index.js.bak", "dist/assets/tmp-x.js",
                                      ".taste-skill/shot.tmp", ".git/HEAD.old", "node_modules/.vite/x.tmp"])
def test_f5_le_cartelle_prodotte_dagli_strumenti_si_ignorano(tmp_path, prodotto):
    fabbrica = FabbricaFinta(esiti_pezzi={
        "skeleton": _scrive(tmp_path, ("server.js", "base")),
        "cars": _scrive(tmp_path, (prodotto, "x"))})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.escalated is False


def test_f6_un_pezzo_che_riscrive_i_suoi_file_non_si_segnala(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={
        "cars": _scrive(tmp_path, ("routes/cars.js", "v1")),
        "page": _scrive(tmp_path, ("public/index.html", "v1"))})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.escalated is False


def test_f7_limite_dichiarato_fra_pezzi_della_stessa_ondata_non_si_sa_chi_ha_scritto(tmp_path):
    """cars e bookings girano insieme: un file di bookings toccato in quell'ondata non e' attribuibile."""
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": _scrive(tmp_path, ("routes/bookings.js", "da cars"))})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert _eventi(esito, "file_check")[1]["foreign"] == {}
    assert esito.escalated is False


def test_f8_i_file_presenti_prima_dello_sciame_non_si_segnalano(tmp_path):
    (tmp_path / "ws").mkdir()
    (tmp_path / "ws" / "vecchio.bak").write_text("c'era gia'")
    esito, _, _ = _esegui(tmp_path)

    assert esito.escalated is False


def test_f9_al_tetto_le_segnalazioni_non_fanno_partire_la_correzione(tmp_path):
    fabbrica = FabbricaFinta(esiti_pezzi={"skeleton": _scrive(tmp_path, ("x.bak", "x"))}, costo=0.01)
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica, budget_usd=0.015)

    assert esito.escalated is False
    assert _eventi(esito, "file_check")[0]["temporary"] == ["x.bak"]


def test_f10_il_prompt_di_correzione_ha_la_sezione_file_solo_se_serve():
    piano = parse_plan(PIANO, routes=("GET /api/cars", "POST /api/bookings"), workers=("worker", "worker_cheap"))

    assert "FILE ISSUES" not in escalation_prompt(PROMPT, piano, "404", {})
    testo = escalation_prompt(PROMPT, piano, None, {}, {"x.bak": "temporary file"})
    assert "FILE ISSUES" in testo and "x.bak: temporary file" in testo
    assert "GATE REJECTION" not in testo and "INCOMPLETE PIECES" not in testo


# -- Skill obbligatorie (P45-D1, 7 nov 2026) --------------------------------

def test_p45_planner_skill_di_design_worker_e_correzione_skill_di_lavoro(tmp_path):
    from tools.load_skill import REQUIRED_SKILLS_PLANNER, REQUIRED_SKILLS_WORKER

    cancello = CancelloFinto(GateVerdict(False, "non partito"), GateVerdict(True))
    _, fabbrica, _ = _esegui(tmp_path, cancello=cancello)

    elenchi = [(a["role"], a["required_skills"]) for a in fabbrica.build_args]
    assert elenchi[0] == ("planner", REQUIRED_SKILLS_PLANNER)
    assert elenchi[-1] == ("planner", REQUIRED_SKILLS_WORKER), "la correzione scrive codice"
    assert all(skill == REQUIRED_SKILLS_WORKER for _, skill in elenchi[1:])


# ── S6 (8 nov): lo scheletro sa di lavorare da solo ───────────────────────
# Nella campagna MVP lo scheletro di 842 ha aspettato 300 s i file dei pezzi che partono dopo
# di lui, perche' il prompt diceva a tutti che altri worker lavoravano in parallelo.

def _piano():
    return parse_plan(PIANO, routes=("GET /api/cars", "POST /api/bookings"), workers=("worker", "worker_cheap"))


def test_s6_lo_scheletro_solo_nella_sua_ondata_non_deve_aspettare_gli_altri():
    piano = _piano()
    testo = worker_prompt(PROMPT, piano, piano.pieces[0])

    assert "only worker running now" in testo
    assert "Do not wait for" in testo
    assert "working in parallel" not in testo


def test_s6_un_pezzo_con_compagni_di_ondata_sa_che_lavorano_in_parallelo():
    piano = _piano()
    testo = worker_prompt(PROMPT, piano, piano.pieces[1])

    assert "working in parallel" in testo
    assert "only worker running now" not in testo


def test_s6_anche_un_pezzo_solo_in_un_ondata_successiva_lavora_da_solo():
    piano = _piano()
    testo = worker_prompt(PROMPT, piano, piano.pieces[3])

    assert "only worker running now" in testo


def test_s6_due_radici_nella_stessa_ondata_lavorano_in_parallelo():
    piano = parse_plan(json.dumps({"style": "s", "contract": {}, "pieces": [
        _pezzo("skeleton", ["start.sh"]), _pezzo("assets", ["public/logo.svg"])]}),
        routes=(), workers=("worker", "worker_cheap"))

    assert "working in parallel" in worker_prompt(PROMPT, piano, piano.pieces[0])


# ── S7 (8 nov): un pezzo fermo al limite non basta per la correzione ──────
# Lo scheletro di DeepSeek arriva spesso a 80 iterazioni con il lavoro fatto; la correzione di
# Opus partiva lo stesso (1,05 $ su 000040). Ora un pezzo `max_iterations` non conta come
# incompleto se il cancello accetta e tutti i suoi file esistono.

def _scrivi(tmp_path, *percorsi):
    for percorso in percorsi:
        file = tmp_path / "ws" / percorso
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("ok")


def test_s7_pezzo_al_limite_con_file_e_cancello_che_accetta_nessuna_correzione(tmp_path):
    _scrivi(tmp_path, "routes/cars.js")
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": "max_iterations"})
    esito, _, cancello = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.escalated is False and _correttori(fabbrica) == []
    assert esito.pieces["cars"] == "max_iterations", "lo stato vero resta nel registro"
    assert len(cancello.chiamate) == 1


def test_s7_pezzo_al_limite_con_un_file_mancante_fa_partire_la_correzione(tmp_path):
    _scrivi(tmp_path, "start.sh")
    fabbrica = FabbricaFinta(esiti_pezzi={"skeleton": "max_iterations"})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.escalated is True
    assert _eventi(esito, "escalation")[0]["incomplete"] == {"skeleton": "max_iterations"}


def test_s7_pezzo_al_limite_con_file_ma_cancello_che_rifiuta_resta_nella_correzione(tmp_path):
    _scrivi(tmp_path, "routes/cars.js")
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": "max_iterations"})
    cancello = CancelloFinto(GateVerdict(False, "non parte"), GateVerdict(True))
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica, cancello=cancello)

    assert _eventi(esito, "escalation")[0]["incomplete"] == {"cars": "max_iterations"}


def test_s7_pezzo_al_limite_con_file_e_cancello_guasto_resta_nella_correzione(tmp_path):
    _scrivi(tmp_path, "routes/cars.js")
    fabbrica = FabbricaFinta(esiti_pezzi={"cars": "max_iterations"})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica, cancello=CancelloFinto(RenderError("Docker spento")))

    assert esito.escalated is True
    assert _eventi(esito, "escalation")[0]["incomplete"] == {"cars": "max_iterations"}


def test_s7_gli_altri_esiti_contano_sempre_come_incompleti_anche_con_i_file(tmp_path):
    _scrivi(tmp_path, "routes/bookings.js")
    fabbrica = FabbricaFinta(esiti_pezzi={"bookings": "loop_detected"})
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica)

    assert esito.escalated is True
    assert "bookings" in _eventi(esito, "escalation")[0]["incomplete"]


# ── Migliorie dello sciame dopo la campagna MVP (8 nov 2026, versione nuova di C) ──
# MS-1 piano tollerante, MS-3 scheletro solo cablaggio, MS-5 sei posti e pezzi lunghi prima,
# MS-6 build dal codice, MS-7 i data-testid del compito copiati e il compito che vince sul piano.

def test_ms1_il_registro_del_piano_nomina_le_note_spostate(tmp_path):
    documento = json.loads(PIANO)
    documento["contract"] = {**FORME, "COMMON": "400 {error}"}
    esito, _, _ = _esegui(tmp_path, fabbrica=FabbricaFinta(piani=(json.dumps(documento),)))

    assert [e["valid"] for e in _eventi(esito, "plan")] == [True]
    assert _eventi(esito, "plan")[0]["notes"] == ["COMMON"]


def test_ms1_il_worker_vede_le_note_comuni_solo_se_ci_sono():
    documento = json.loads(PIANO)
    documento["notes"] = {"COMMON": "every error is 400 {error: string}"}
    piano = parse_plan(json.dumps(documento), routes=("GET /api/cars", "POST /api/bookings"),
                       workers=("worker", "worker_cheap"))

    assert "SHARED NOTES" in worker_prompt(PROMPT, piano, piano.pieces[1])
    assert "COMMON: every error is 400 {error: string}" in worker_prompt(PROMPT, piano, piano.pieces[1])
    assert "SHARED NOTES" not in worker_prompt(PROMPT, _piano(), _piano().pieces[1])


def test_ms1_il_planner_sa_che_le_chiavi_del_contratto_sono_solo_rotte():
    testo = planner_prompt(PROMPT, REGISTRO, ("GET /api/cars", "POST /api/bookings"))

    assert '"notes"' in testo
    assert "Keys of \"contract\" are routes only" in testo


def test_ms3_lo_scheletro_e_solo_cablaggio_e_finisce_quando_la_build_passa():
    testo = planner_prompt(PROMPT, REGISTRO, ("GET /api/cars", "POST /api/bookings"))

    assert "only the wiring" in testo
    assert "no visual components and no section content" in testo
    assert "does not inspect the site visually" in testo


def test_ms5_i_posti_predefiniti_sono_quelli_della_sandbox():
    import inspect

    import config

    assert inspect.signature(run_swarm).parameters["max_parallel"].default == config.DOCKER_MAX_CONCURRENT


def test_ms5_nella_stessa_ondata_partono_prima_kimi_poi_l_interfaccia_poi_i_server(tmp_path):
    descrizione = lambda id_, n: {**_pezzo(id_, [f"{id_}.js"], ["skeleton"]), "description": f"descrizione di {id_} " + "x " * n}
    piano = json.dumps({"style": "s", "contract": FORME, "pieces": [
        _pezzo("skeleton", ["start.sh"]),
        {**descrizione("server", 50), "routes": ["GET /api/cars", "POST /api/bookings"]},
        descrizione("corta", 5),
        descrizione("lunga", 40),
        {**descrizione("kimi", 1), "worker": "worker"},
    ]})
    _, fabbrica, _ = _esegui(tmp_path, fabbrica=FabbricaFinta(piani=(piano,)), max_parallel=1)

    assert fabbrica.pezzi_costruiti() == ["skeleton", "kimi", "lunga", "corta", "server"]


def test_ms6_il_planner_non_crea_pezzi_di_build_o_di_verifica():
    testo = planner_prompt(PROMPT, REGISTRO, ("GET /api/cars", "POST /api/bookings"))

    assert "Do not create build, integration or verification pieces" in testo


class BuildFinta:
    def __init__(self, *esiti):
        self.esiti = list(esiti) or [{"exit_code": 0, "stdout": "built", "stderr": ""}]
        self.chiamate = []

    def __call__(self, workspace):
        self.chiamate.append(Path(workspace))
        esito = self.esiti[min(len(self.chiamate) - 1, len(self.esiti) - 1)]
        if isinstance(esito, BaseException):
            raise esito
        return esito


def test_ms6_la_build_gira_una_volta_dopo_l_ultimo_pezzo_e_prima_del_cancello(tmp_path):
    ordine = []
    build = BuildFinta()
    cancello = CancelloFinto()

    def build_registrata(ws):
        ordine.append(("build", time.monotonic()))
        return build(ws)

    def cancello_registrato(ws, out):
        ordine.append(("cancello", time.monotonic()))
        return cancello(ws, out)

    esito, fabbrica, _ = _esegui(tmp_path, cancello=cancello_registrato, build_site=build_registrata)

    assert build.chiamate == [tmp_path / "ws"]
    assert [nome for nome, _ in ordine] == ["build", "cancello"]
    # Revisione dell'8 nov: la build deve partire dopo la fine di ogni pezzo, non solo prima del cancello.
    assert len(fabbrica.pezzi_costruiti()) == 4
    assert ordine[0][1] >= max(fine for _, fine in fabbrica.fini)
    assert _eventi(esito, "build") == [{"event": "build", "phase": "initial", "exit_code": 0,
                                        "skipped": False, "error": None}]
    assert esito.escalated is False


def test_ms6_senza_script_di_build_la_build_si_registra_come_saltata(tmp_path):
    esito, _, _ = _esegui(tmp_path)

    assert _eventi(esito, "build")[0]["skipped"] is True
    assert esito.escalated is False


def test_ms6_una_build_fallita_fa_partire_la_correzione_con_l_errore(tmp_path):
    build = BuildFinta({"exit_code": 1, "stdout": "", "stderr": "src/App.jsx: Unexpected token"},
                       {"exit_code": 0, "stdout": "built", "stderr": ""})
    esito, fabbrica, _ = _esegui(tmp_path, build_site=build)

    assert esito.escalated is True
    correzione = _correttori(fabbrica)[0].prompts[0]
    assert "BUILD FAILURE" in correzione and "src/App.jsx: Unexpected token" in correzione
    assert [e["phase"] for e in _eventi(esito, "build")] == ["initial", "after_escalation"]


def test_ms6_un_guasto_della_build_si_registra_e_non_fa_partire_la_correzione(tmp_path):
    esito, _, _ = _esegui(tmp_path, build_site=BuildFinta(RuntimeError("docker assente")))

    riga = _eventi(esito, "build")[0]
    assert riga["error"] == "docker assente" and riga["exit_code"] is None
    assert esito.escalated is False


def test_ms6_al_tetto_la_build_gira_ma_la_correzione_no(tmp_path):
    build = BuildFinta({"exit_code": 1, "stdout": "", "stderr": "rotto"})
    fabbrica = FabbricaFinta(costo=0.3)
    esito, _, _ = _esegui(tmp_path, fabbrica=fabbrica, budget_usd=1.0, build_site=build)

    assert len(build.chiamate) == 1
    assert esito.escalated is False


def test_ms6_il_prompt_di_correzione_ha_la_sezione_build_solo_se_serve():
    piano = _piano()

    assert "BUILD FAILURE" not in escalation_prompt(PROMPT, piano, "404", {})
    testo = escalation_prompt(PROMPT, piano, None, {}, build_error="exit 1: boom")
    assert "BUILD FAILURE" in testo and "exit 1: boom" in testo
    assert "npm run build" in testo


def test_ms6_la_build_predefinita_salta_un_workspace_senza_script_di_build(tmp_path):
    from swarm import build_site

    assert build_site(tmp_path) is None
    (tmp_path / "package.json").write_text('{"scripts": {"start": "node server.js"}}')
    assert build_site(tmp_path) is None
    (tmp_path / "package.json").write_text("non json")
    assert build_site(tmp_path) is None


def test_ms7_il_planner_copia_parola_per_parola_i_data_testid_del_compito():
    testo = planner_prompt(PROMPT, REGISTRO, ("GET /api/cars", "POST /api/bookings"))

    assert "copy verbatim" in testo and "data-testid" in testo
    assert "do not add conditions the task does not state" in testo


def test_ms7_il_worker_sa_che_il_compito_vince_sulla_descrizione_del_pezzo():
    piano = _piano()
    testo = worker_prompt(PROMPT, piano, piano.pieces[1])

    assert "If YOUR PIECE contradicts the TASK" in testo
    assert "follow the TASK" in testo


def test_ms6_la_build_predefinita_gira_nella_sandbox_senza_rete(tmp_path, monkeypatch):
    """Revisione dell'8 nov: il ramo che esegue davvero la build, con un esecutore finto."""
    import config
    import swarm

    creati = []

    class EsecutoreFinto:
        def __init__(self, workspace, **opzioni):
            self.workspace, self.opzioni, self.comandi = workspace, opzioni, []
            creati.append(self)

        def run(self, command):
            self.comandi.append(command)
            return {"exit_code": 0, "stdout": "built", "stderr": ""}

    monkeypatch.setattr(swarm, "DockerExecutor", EsecutoreFinto)
    (tmp_path / "package.json").write_text('{"scripts": {"build": "vite build"}}')

    esito = swarm.build_site(tmp_path)

    assert esito == {"exit_code": 0, "stdout": "built", "stderr": ""}
    assert len(creati) == 1 and creati[0].workspace == str(tmp_path)
    assert creati[0].comandi == ["npm run build"]
    assert creati[0].opzioni["network"] == "none"
    assert creati[0].opzioni["image"] == config.DOCKER_IMAGE
    assert creati[0].opzioni["timeout"] == config.EXEC_TIMEOUT


@pytest.mark.parametrize("esito_build", [{"exit_code": None}, {"exit_code": "boh"}, {"stdout": "x"},
                                          {"exit_code": True}])
def test_ms6_un_esito_di_build_malformato_e_un_guasto_registrato(tmp_path, esito_build):
    """Revisione dell'8 nov: un esito senza codice intero non fa cadere lo sciame."""
    esito, _, _ = _esegui(tmp_path, build_site=BuildFinta(esito_build))

    riga = _eventi(esito, "build")[0]
    assert riga["exit_code"] is None and "exit_code" in riga["error"]
    assert esito.status == "completed" and esito.escalated is False
