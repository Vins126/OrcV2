"""M2s.4b: tutto passa da OpenRouter; costo riportato e fornitore che ha risposto nel record.

Nota di design (tesi):
    L'infrastruttura e' una sola, OpenRouter, con una sola chiave. Un modello ha
    un listino e, facoltativo, un **fornitore fissato** (`provider_order`): dietro
    un aggregatore lo stesso modello puo' essere servito da fornitori diversi,
    anche quantizzati, e senza fissarlo due run dello stesso modello potrebbero
    non essere confrontabili. Il record porta il costo che il fornitore dichiara
    (`reported_cost`) e chi ha risposto (`served_by`); il costo del ledger resta
    quello calcolato sul listino.

    I test costruiscono il registro da un dizionario con prezzi tondi, cosi' i
    costi attesi si verificano a mente. Solo l'ultimo gruppo carica il
    `models.toml` reale.
"""

import json
import pathlib
import subprocess
from types import SimpleNamespace as NS

import pytest

import campaign
from accounting import (
    MalformedRegistry,
    ModelNotFound,
    ModelRegistry,
    UnitNotFound,
    UsageRecord,
)
from accounting.errors import InvalidUsage
from accounting.ledger import RunLedger
from accounting.mappers import OpenAIChatCompletionsUsageMapper
from agent_factory import BACKEND_PER_PROVIDER, AgentFactory, UnsupportedProvider
from llm_gateway import OpenAIChatGateway
from run_reporter import RunReporter

RADICE = pathlib.Path(__file__).resolve().parent.parent

UNITA = {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
         "cached_input_tokens": 1_000_000, "cache_write_tokens": 1_000_000}

CONFIG = {
    "units": UNITA,
    "providers": {
        "openrouter": {"base_url": "https://agg.test/api/v1", "api_key_env": "CHIAVE_OR"},
    },
    "models": {
        # Con fornitore fissato.
        "grande": {
            "provider": "openrouter",
            "api_model": "casa/grande",
            "provider_order": ["casa-diretta"],
            "capabilities": ["reasoning", "code"],
            "prices": {"input_tokens": 3.0, "output_tokens": 15.0, "cached_input_tokens": 0.3,
                       "cache_write_tokens": 1.0},
        },
        # Fornitore fissato E parametro di richiesta aggiuntivo (cache esplicita).
        "ibrido": {
            "provider": "openrouter",
            "api_model": "casa/ibrido",
            "provider_order": ["casa-diretta"],
            "extra_body": {"cache_control": {"type": "ephemeral"}},
            "capabilities": ["code"],
            "prices": {"input_tokens": 3.0, "output_tokens": 15.0},
        },
        # Solo il parametro di richiesta, nessun fornitore fissato.
        "solo_extra": {
            "provider": "openrouter",
            "api_model": "casa/solo-extra",
            "extra_body": {"cache_control": {"type": "ephemeral"}},
            "capabilities": ["code"],
            "prices": {"input_tokens": 3.0, "output_tokens": 15.0},
        },
        # Senza fornitore fissato.
        "piccolo": {
            "provider": "openrouter",
            "api_model": "casa/piccolo",
            "capabilities": ["code"],
            "prices": {"input_tokens": 0.3, "output_tokens": 1.2},
        },
    },
    "roles": {
        "pesante": {"model": "grande", "requires": ["reasoning"]},
        "leggero": {"model": "piccolo", "requires": ["code"]},
        "ibrido": {"model": "ibrido", "requires": ["code"]},
        "solo_extra": {"model": "solo_extra", "requires": ["code"]},
    },
}


def _config():
    """Copia profonda della configurazione base."""
    return json.loads(json.dumps(CONFIG))


@pytest.fixture
def registro():
    return ModelRegistry(CONFIG)


# ── Registro: un listino per modello, con fornitore fissato facoltativo ───

def test_r1_il_costo_usa_il_listino_del_modello(registro):
    # 1M input a 3.00 = 3.00; 2M output a 15.00 = 30.00
    assert registro.cost("grande", "input_tokens", 1_000_000) == pytest.approx(3.0)
    assert registro.cost("grande", "output_tokens", 2_000_000) == pytest.approx(30.0)


def test_r2_api_model_e_il_nome_con_cui_openrouter_conosce_il_modello(registro):
    assert registro.api_model_for("grande") == "casa/grande"
    assert registro.api_model_for("piccolo") == "casa/piccolo"


def test_r3_provider_order_solo_dove_dichiarato(registro):
    assert registro.provider_order_for("grande") == ["casa-diretta"]
    assert registro.provider_order_for("piccolo") is None


def test_r4_un_prezzo_assente_non_si_inventa(registro):
    # `piccolo` non ha prezzo di scrittura in cache: il consumo non e' prezzabile, non gratuito.
    with pytest.raises(UnitNotFound):
        registro.cost("piccolo", "cache_write_tokens", 1_000_000)


@pytest.mark.parametrize("difetto, cambia", [
    ("fornitore non dichiarato", lambda m: m.update(provider="ignoto")),
    ("senza prezzi", lambda m: m.update(prices={})),
    ("prezzo negativo", lambda m: m.update(prices={"input_tokens": -1.0})),
    ("unita' senza base", lambda m: m.update(prices={"nuvole": 1.0})),
    ("api_model vuoto", lambda m: m.update(api_model=" ")),
    ("provider_order non e' una lista", lambda m: m.update(provider_order="casa")),
    ("provider_order vuoto", lambda m: m.update(provider_order=[])),
    ("provider_order con voci vuote", lambda m: m.update(provider_order=[""])),
])
def test_r5_un_modello_malformato_e_rifiutato_al_caricamento(difetto, cambia):
    dati = _config()
    cambia(dati["models"]["grande"])
    with pytest.raises(MalformedRegistry):
        ModelRegistry(dati)


# ── Report: costo calcolato e costo riportato, affiancati ─────────────────

def _scrivi_run(runs_root, run_id, record):
    cartella = runs_root / run_id
    cartella.mkdir(parents=True)
    (cartella / "summary.json").write_text(json.dumps({"run_id": run_id}))
    with open(cartella / "usage.jsonl", "w") as f:
        f.write(json.dumps({"record": record}) + "\n")


def _manifesto(percorso, run_ids):
    with open(percorso, "w") as f:
        for i, run_id in enumerate(run_ids):
            f.write(json.dumps({"task_id": "t", "rep": i, "run_id": run_id, "status": "completed",
                                "verified": True, "success": True}) + "\n")


def test_c1_il_report_somma_il_costo_riportato_solo_dove_c_e_e_lo_tiene_distinto_dal_calcolato(tmp_path, registro):
    runs = tmp_path / "runs"
    base = {"model": "grande", "quantities": {"input_tokens": 1_000_000}}
    _scrivi_run(runs, "r0", {**base, "reported_cost": 3.10})
    _scrivi_run(runs, "r1", {**base, "reported_cost": 2.90})
    _scrivi_run(runs, "r2", dict(base))                       # record senza costo riportato
    manifesto = tmp_path / "c.jsonl"
    _manifesto(manifesto, ["r0", "r1", "r2"])

    esito = campaign.report(manifesto, runs, registro)

    assert esito.total_cost == pytest.approx(9.0)         # calcolato: 3 x 3.00
    assert esito.reported_cost == pytest.approx(6.0)      # riportato: 3.10 + 2.90, solo 2 record
    assert esito.reported_records == 2


def test_c2_senza_nessun_costo_riportato_il_totale_riportato_e_none_e_non_zero(tmp_path, registro):
    runs = tmp_path / "runs"
    _scrivi_run(runs, "r0", {"model": "grande", "quantities": {"input_tokens": 10}})
    manifesto = tmp_path / "c.jsonl"
    _manifesto(manifesto, ["r0"])

    esito = campaign.report(manifesto, runs, registro)

    assert esito.reported_cost is None
    assert esito.reported_records == 0


def test_c3_il_report_conta_tra_i_non_prezzati_un_modello_che_non_e_piu_a_registro(tmp_path, registro):
    runs = tmp_path / "runs"
    _scrivi_run(runs, "r0", {"model": "opus-5", "quantities": {"input_tokens": 10}})
    manifesto = tmp_path / "c.jsonl"
    _manifesto(manifesto, ["r0"])

    assert campaign.report(manifesto, runs, registro).unpriced_records == 1


def test_c4_il_listino_non_dipende_dal_billing_provider_dei_record_vecchi(tmp_path, registro):
    """Record di campagne passate portano `billing_provider` di infrastrutture scollegate."""
    runs = tmp_path / "runs"
    base = {"model": "grande", "quantities": {"input_tokens": 1_000_000}}
    _scrivi_run(runs, "r0", {**base, "billing_provider": "anthropic"})
    _scrivi_run(runs, "r1", {**base, "billing_provider": "litellm"})
    manifesto = tmp_path / "c.jsonl"
    _manifesto(manifesto, ["r0", "r1"])

    esito = campaign.report(manifesto, runs, registro)

    assert esito.total_cost == pytest.approx(6.0)
    assert esito.unpriced_records == 0


# ── Mapper: costo riportato, fornitore e scrittura in cache ───────────────

def _risposta(usage, **altro):
    return NS(id="gen-1", usage=usage,
              choices=[NS(finish_reason="stop", message=NS(tool_calls=None))], **altro)


def test_m1_il_mapper_legge_usage_cost_e_il_fornitore_che_ha_risposto():
    usage = NS(prompt_tokens=100, completion_tokens=10, cost=0.000678,
               prompt_tokens_details=None, completion_tokens_details=None)

    record = OpenAIChatCompletionsUsageMapper.to_record(
        _risposta(usage, provider="Moonshot AI"), model="grande", latency_s=0.1)

    assert record.reported_cost == pytest.approx(0.000678)
    assert record.served_by == "Moonshot AI"


def test_m2_se_il_fornitore_non_li_riporta_i_campi_sono_none_non_zero():
    usage = NS(prompt_tokens=100, completion_tokens=10,
               prompt_tokens_details=None, completion_tokens_details=None)

    record = OpenAIChatCompletionsUsageMapper.to_record(
        _risposta(usage), model="grande", latency_s=0.1)

    assert record.reported_cost is None
    assert record.served_by is None


def test_m3_la_scrittura_in_cache_si_scorpora_dall_input_senza_doppio_conteggio():
    """prompt 1000 = 600 normali + 300 letti dalla cache + 100 scritti nella cache.

    Ipotesi (da confermare alla prima chiamata vera su OpenRouter): `prompt_tokens`
    li include entrambi, come include i letti. Se non fosse cosi' il totale
    conterebbe 100 token due volte.
    """
    usage = NS(prompt_tokens=1000, completion_tokens=50,
               prompt_tokens_details=NS(cached_tokens=300, cache_write_tokens=100),
               completion_tokens_details=None)

    record = OpenAIChatCompletionsUsageMapper.to_record(
        _risposta(usage), model="grande", latency_s=0.1)

    assert record.quantities == {"input_tokens": 600, "cached_input_tokens": 300,
                                 "cache_write_tokens": 100, "output_tokens": 50}


def test_m4_un_costo_riportato_negativo_o_non_numerico_e_rifiutato():
    for valore in (-0.1, float("nan"), "0.1"):
        with pytest.raises(InvalidUsage):
            UsageRecord(model="m", quantities={}, reported_cost=valore)  # pyright: ignore[reportArgumentType]


def test_m5_un_costo_riportato_strano_non_fa_perdere_il_record_dei_token():
    """La chiamata e' gia' stata pagata: un campo accessorio invalido diventa None."""
    usage = NS(prompt_tokens=100, completion_tokens=10, cost="boh",
               prompt_tokens_details=None, completion_tokens_details=None)

    record = OpenAIChatCompletionsUsageMapper.to_record(
        _risposta(usage), model="grande", latency_s=0.1)

    assert record.reported_cost is None
    assert record.quantities == {"input_tokens": 100, "output_tokens": 10}


# ── Ledger: schema 3 ──────────────────────────────────────────────────────

def test_l1_il_ledger_e_alla_versione_3_e_scrive_i_campi_nuovi(tmp_path):
    ledger = RunLedger(root=tmp_path, task="t", agent_id="a", role="worker")
    ledger.append_usage(UsageRecord(
        model="grande", quantities={"input_tokens": 1}, reported_cost=0.25, served_by="Moonshot AI"))

    riga = json.loads((ledger.run_dir / "usage.jsonl").read_text().splitlines()[0])

    assert RunLedger.SCHEMA_VERSION == 4
    assert riga["schema_version"] == 4
    assert riga["record"]["reported_cost"] == 0.25
    assert riga["record"]["served_by"] == "Moonshot AI"


# ── Fabbrica: un solo backend, OpenRouter ─────────────────────────────────

class ReporterMuto(RunReporter):
    def emit(self, summary, events, ledger_path, agent_message=None) -> str:
        return ""


@pytest.fixture
def fabbrica(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIAVE_OR", "chiave-finta")
    return AgentFactory(
        ModelRegistry(CONFIG), runs_root=tmp_path / "runs", workspaces_root=tmp_path / "ws",
        tools_builder=lambda percorso, **_: [], reporter=ReporterMuto())


def test_f1_il_ruolo_va_su_openrouter_col_nome_del_modello_e_il_fornitore_fissato(fabbrica):
    gw = fabbrica.build("pesante").gateway

    assert isinstance(gw, OpenAIChatGateway)
    assert str(gw.client.base_url).startswith("https://agg.test")
    assert (gw.api_model, gw.api_provider, gw.billing_provider) == (
        "casa/grande", "openrouter", "openrouter")
    assert gw.model == "grande"                                # la chiave di contabilita' non cambia
    assert gw.extra_body == {"provider": {"order": ["casa-diretta"], "allow_fallbacks": False}}


def test_f2_senza_provider_order_non_si_invia_alcun_vincolo(fabbrica):
    assert fabbrica.build("leggero").gateway.extra_body is None


def test_f3_chiave_mancante_nomina_fornitore_e_variabile_e_non_crea_cartelle(fabbrica, monkeypatch, tmp_path):
    monkeypatch.delenv("CHIAVE_OR")

    with pytest.raises(RuntimeError) as errore:
        fabbrica.build("pesante")

    assert "openrouter" in str(errore.value) and "CHIAVE_OR" in str(errore.value)
    assert not (tmp_path / "ws").exists() or not any((tmp_path / "ws").iterdir())


def test_f4_openrouter_e_l_unico_backend_e_parla_il_formato_openai():
    assert set(BACKEND_PER_PROVIDER) == {"openrouter"}
    assert BACKEND_PER_PROVIDER["openrouter"].gateway is OpenAIChatGateway


def test_f5_un_fornitore_senza_backend_e_un_errore_parlante(tmp_path, monkeypatch):
    dati = _config()
    dati["providers"]["altro"] = {"api_key_env": "CHIAVE_ALTRO"}
    dati["models"]["piccolo"]["provider"] = "altro"
    monkeypatch.setenv("CHIAVE_ALTRO", "x")
    fabbrica = AgentFactory(ModelRegistry(dati), runs_root=tmp_path / "runs",
                            workspaces_root=tmp_path / "ws", tools_builder=lambda p, **_: [])

    with pytest.raises(UnsupportedProvider, match="altro"):
        fabbrica.build("leggero")


def test_f6_la_fabbrica_non_conosce_ne_il_proxy_ne_le_strade():
    import agent_factory
    import config
    for nome in ("CORPO_RISPOSTA_FRESCA", "PROXY_CACHE_AMMESSE", "_client_anthropic"):
        assert not hasattr(agent_factory, nome)
    assert not hasattr(config, "LLMSettings") and not hasattr(config, "load_llm_settings")
    argomenti = AgentFactory.__init__.__code__.co_varnames + AgentFactory.build.__code__.co_varnames
    assert "proxy" not in argomenti and "route" not in argomenti


# ── Punti d'ingresso ──────────────────────────────────────────────────────

def test_i1_la_campagna_non_conosce_piu_proxy_ne_strade():
    parser = campaign.build_parser()

    for opzione in (["--via-proxy"], ["--proxy-cache", "use"], ["--route", "x"]):
        with pytest.raises(SystemExit):
            parser.parse_args(["run", "--budget-usd", "1", "--max-total-usd", "1", *opzione])


def test_i2_main_non_conosce_piu_proxy_model_ne_strade():
    from main import build_parser
    parser = build_parser()

    for opzione in (["--via-proxy"], ["--model", "x"], ["--route", "x"]):
        with pytest.raises(SystemExit):
            parser.parse_args([*opzione, "task"])


def _file_versionati_o_da_versionare():
    """File tracciati o non ignorati: e' cio' che finisce nel repository pubblico."""
    uscita = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=RADICE, capture_output=True, text=True, check=True).stdout
    return [RADICE / riga for riga in uscita.splitlines() if (RADICE / riga).is_file()]


def test_i3_nel_codice_e_nei_test_non_resta_nessun_riferimento_a_litellm_o_alle_strade():
    cercati = ("litellm", "LLMSettings", "load_llm_settings", "ORC2_BASE_URL", "ORC2_API_KEY",
               "ORC2_MODEL", "via_proxy", "via-proxy", "proxy_cache", "proxy-cache",
               "RouteNotFound", "routes_of", "route_for", "--route")
    codice = [p for p in _file_versionati_o_da_versionare()
              if p.suffix in (".py", ".toml", ".example") and p.name != "test_openrouter.py"
              and "campaigns/data" not in str(p)]
    trovati = [(p.name, c) for p in codice
               for c in cercati if c.lower() in p.read_text(errors="ignore").lower()]
    assert trovati == []


def test_i4_la_chiave_non_compare_in_nessun_file_versionato():
    """Una chiave OpenRouter ha un prefisso noto: nel repository pubblico non deve esserci.

    Il prefisso e' scritto in due pezzi perche' questo stesso file e' versionato e non
    deve contenerlo per intero.
    """
    prefisso = "sk-or-" + "v1-"
    trovati = [p.name for p in _file_versionati_o_da_versionare()
               if prefisso in p.read_text(errors="ignore")]
    assert trovati == []


def test_i5_il_file_delle_infrastrutture_scollegate_nomina_ognuna_e_dice_come_ricollegarla():
    percorso = RADICE / "docs" / "INFRASTRUTTURE_SCOLLEGATE.md"
    assert percorso.exists()
    testo = percorso.read_text().lower()
    for infrastruttura in ("anthropic", "moonshot", "minimax", "openai", "tripo", "litellm"):
        assert infrastruttura in testo, infrastruttura
    assert "ricollegare" in testo and "perche'" in testo


# ── Il models.toml reale ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def reale():
    return ModelRegistry.from_file("models.toml")


def test_p1_il_pool_e_i_ruoli_sono_quelli_decisi(reale):
    """Rosa di D38 e D47: Opus forte, GPT-6.1 Sol intermedio, DeepSeek V4.1 Flash economico.

    Kimi K3 e MiniMax M3 restano nel registro solo per prezzare le run gia' fatte:
    nessun ruolo li usa.
    """
    assert reale.model_for("planner") == "opus-5-5"
    assert reale.model_for("worker") == "gpt-6-1-sol"
    assert reale.model_for("worker_cheap") == "deepseek-v4-1-flash"
    for tolto in ("opus-5", "minimax-m2-7"):
        assert tolto not in reale.models
    for fuori_rosa in ("kimi-k3", "minimax-m3"):
        assert fuori_rosa in reale.models
        assert fuori_rosa not in {reale.model_for(r) for r in ("planner", "worker", "worker_cheap")}


def test_p2_un_solo_fornitore_openrouter_con_la_sua_chiave(reale):
    assert set(reale.providers) == {"openrouter"}
    assert reale.providers["openrouter"]["api_key_env"] == "ORC2_OPENROUTER_KEY"
    assert reale.providers["openrouter"]["base_url"] == "https://openrouter.ai/api/v1"
    assert {dati["provider"] for dati in reale.models.values()} == {"openrouter"}


def test_p3_i_nomi_dei_modelli_su_openrouter_sono_quelli_verificati(reale):
    assert reale.api_model_for("opus-5-5") == "anthropic/claude-opus-5.5"
    assert reale.api_model_for("kimi-k3") == "moonshotai/kimi-k3"
    assert reale.api_model_for("minimax-m3") == "minimax/minimax-m3"
    assert reale.api_model_for("gpt-6-1-sol") == "openai/gpt-6.1-sol"
    assert reale.api_model_for("deepseek-v4-pro") == "deepseek/deepseek-v4-pro-0813"
    assert reale.api_model_for("deepseek-v4-1-flash") == "deepseek/deepseek-v4.1-flash-1017"
    assert reale.api_model_for("glm-5-3-flash") == "z-ai/glm-5.3-flash"
    assert reale.api_model_for("gemini-4-argon") == "google/gemini-4-argon"
    assert reale.api_model_for("gemini-3-8-flash") == "google/gemini-3.8-flash"
    assert reale.api_model_for("text-embedding-3-small") == "openai/text-embedding-3-small"


def test_p4_listini_verificati_il_10_ottobre_2026_sull_endpoint_fissato(reale):
    # dollari per milione: (input, output, lettura cache)
    attesi = {"opus-5-5": (4.0, 20.0, 0.20), "kimi-k3": (3.0, 15.0, 0.30),
              "minimax-m3": (0.30, 1.20, 0.06),
              # rosa D38, letti il 19 ottobre 2026
              "gpt-6-1-sol": (2.0, 10.0, 0.10), "deepseek-v4-pro": (0.66, 1.98, 0.022),
              "glm-5-3-flash": (0.15, 0.50, 0.03), "gemini-4-argon": (2.0, 10.0, 0.10),
              "gemini-3-8-flash": (0.75, 3.75, 0.075),
              # D47, letto il 21 ottobre 2026 (prezzo fuori dalla fascia oraria doppia)
              "deepseek-v4-1-flash": (0.15, 0.60, 0.003)}
    for modello, (i, o, c) in attesi.items():
        assert reale.cost(modello, "input_tokens", 1_000_000) == pytest.approx(i)
        assert reale.cost(modello, "output_tokens", 1_000_000) == pytest.approx(o)
        assert reale.cost(modello, "cached_input_tokens", 1_000_000) == pytest.approx(c)
    assert reale.cost("opus-5-5", "cache_write_tokens", 1_000_000) == pytest.approx(5.0)
    assert reale.cost("text-embedding-3-small", "input_tokens", 1_000_000) == pytest.approx(0.02)
    # Sull'endpoint Moonshot di OpenRouter non e' elencato un prezzo di scrittura in cache:
    # un consumo di quel tipo risulta non prezzato, non coperto da un numero non verificato.
    with pytest.raises(UnitNotFound):
        reale.cost("kimi-k3", "cache_write_tokens", 1)


def test_p5_il_fornitore_e_fissato_per_tutti_i_modelli_di_chat_ma_non_per_l_embedding(reale):
    """Senza fornitore fissato il listino puo' non descrivere piu' cio' che si paga.

    Lo si e' visto il 12 ottobre 2026 con M3: OpenRouter lo ha instradato a CoreWeave (fp4,
    0.23 / 0.96) e il costo riportato e' risultato il 21% sotto il listino (0.30 / 1.20).
    """
    assert reale.provider_order_for("opus-5-5") == ["anthropic"]
    assert reale.provider_order_for("kimi-k3") == ["moonshotai/mxfp4"]
    assert reale.provider_order_for("minimax-m3") == ["minimax/fp8"]
    assert reale.provider_order_for("gpt-6-1-sol") == ["openai"]
    assert reale.provider_order_for("deepseek-v4-pro") == ["deepseek"]
    assert reale.provider_order_for("deepseek-v4-1-flash") == ["deepseek"]
    assert reale.provider_order_for("glm-5-3-flash") == ["z-ai/fp8"]
    assert reale.provider_order_for("gemini-4-argon") == ["google-ai-studio"]
    assert reale.provider_order_for("gemini-3-8-flash") == ["google-ai-studio"]
    assert reale.provider_order_for("text-embedding-3-small") is None


# ── Parametri di richiesta per modello: `extra_body` (cache di Opus) ──────
#
# Nota di design (tesi):
#    Anthropic non mette in cache da solo: la richiesta deve contenere `cache_control`. Kimi e
#    MiniMax invece usano la cache in automatico. La differenza sta nel MODELLO, quindi vive in
#    `models.toml` come campo facoltativo `extra_body`, e non in un `if` nel codice (decisione D9).

def test_x1_il_registro_espone_l_extra_body_dichiarato_e_none_altrove(registro):
    assert registro.extra_body_for("solo_extra") == {"cache_control": {"type": "ephemeral"}}
    assert registro.extra_body_for("ibrido") == {"cache_control": {"type": "ephemeral"}}
    assert registro.extra_body_for("grande") is None
    assert registro.extra_body_for("piccolo") is None


def test_x2_extra_body_di_un_modello_ignoto_e_un_errore_parlante(registro):
    with pytest.raises(ModelNotFound):
        registro.extra_body_for("inventato")


@pytest.mark.parametrize("difetto, valore", [
    ("non e' una tabella (stringa)", "cache"),
    ("non e' una tabella (lista)", [{"cache_control": {}}]),
    ("usa la chiave riservata `provider`", {"provider": {"order": ["altro"]}}),
])
def test_x3_un_extra_body_malformato_e_rifiutato_al_caricamento(difetto, valore):
    """`provider` e' riservato: lo scrive la fabbrica da `provider_order`. Permettere di
    dichiararlo qui lascerebbe sovrascrivere in silenzio il fornitore fissato."""
    dati = _config()
    dati["models"]["solo_extra"]["extra_body"] = valore
    with pytest.raises(MalformedRegistry, match="extra_body"):
        ModelRegistry(dati)


def test_x4_la_fabbrica_unisce_extra_body_e_fornitore_fissato(fabbrica):
    gw = fabbrica.build("ibrido").gateway

    assert gw.extra_body == {
        "provider": {"order": ["casa-diretta"], "allow_fallbacks": False},
        "cache_control": {"type": "ephemeral"},
    }


def test_x5_con_il_solo_extra_body_non_si_invia_alcun_vincolo_di_fornitore(fabbrica):
    gw = fabbrica.build("solo_extra").gateway

    assert gw.extra_body == {"cache_control": {"type": "ephemeral"}}


def test_x6_la_fabbrica_non_condivide_i_dizionari_con_il_registro(fabbrica):
    """Due agenti costruiti dallo stesso modello non devono potersi modificare a vicenda."""
    primo = fabbrica.build("ibrido").gateway
    primo.extra_body["cache_control"]["type"] = "modificato"
    primo.extra_body["provider"]["order"].append("intruso")

    secondo = fabbrica.build("ibrido").gateway

    assert secondo.extra_body["cache_control"] == {"type": "ephemeral"}
    assert secondo.extra_body["provider"]["order"] == ["casa-diretta"]
    assert fabbrica.registry.extra_body_for("ibrido") == {"cache_control": {"type": "ephemeral"}}
    assert fabbrica.registry.provider_order_for("ibrido") == ["casa-diretta"]


def test_p6_solo_opus_ha_la_cache_esplicita_nel_models_toml_reale(reale):
    assert reale.extra_body_for("opus-5-5") == {"cache_control": {"type": "ephemeral"}}
    for modello in ("kimi-k3", "minimax-m3", "text-embedding-3-small"):
        assert reale.extra_body_for(modello) is None, modello


def test_p7_la_richiesta_di_opus_porta_fornitore_fissato_e_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("ORC2_OPENROUTER_KEY", "chiave-finta")
    fabbrica_reale = AgentFactory(
        ModelRegistry.from_file("models.toml"), runs_root=tmp_path / "runs",
        workspaces_root=tmp_path / "ws", tools_builder=lambda percorso, **_: [], reporter=ReporterMuto())

    planner = fabbrica_reale.build("planner").gateway
    worker = fabbrica_reale.build("worker").gateway
    assert isinstance(planner, OpenAIChatGateway) and isinstance(worker, OpenAIChatGateway)

    assert planner.extra_body == {
        "provider": {"order": ["anthropic"], "allow_fallbacks": False},
        "cache_control": {"type": "ephemeral"},
    }
    assert worker.extra_body == {
        "provider": {"order": ["openai"], "allow_fallbacks": False}}


# ── Rilievi della revisione: chiavi riservate e valori serializzabili ─────
#
# Nota di design (tesi):
#    L'SDK unisce `extra_body` al corpo della richiesta e, a chiavi uguali, vince `extra_body`.
#    Quindi non solo `provider` ma ogni campo che la fabbrica o il gateway scrivono da se'
#    (`model`, `messages`, `tools`...) non si puo' dichiarare in configurazione: una riga di
#    `models.toml` cambierebbe in silenzio il modello realmente chiamato, mentre il ledger lo
#    attribuirebbe a un altro.

@pytest.mark.parametrize("chiave", ["model", "messages", "tools", "tool_choice", "stream"])
def test_x7_le_chiavi_che_la_richiesta_scrive_da_se_sono_riservate(chiave):
    dati = _config()
    dati["models"]["solo_extra"]["extra_body"] = {chiave: "qualcosa", "cache_control": {"type": "ephemeral"}}

    with pytest.raises(MalformedRegistry, match="riservat"):
        ModelRegistry(dati)


@pytest.mark.parametrize("valore", [
    __import__("datetime").datetime(2026, 10, 12, 8, 0, 0),   # TOML ammette date e ore
    {1, 2},                                                    # un insieme non e' JSON
    b"byte",
])
def test_x8_un_extra_body_non_serializzabile_in_json_e_rifiutato_al_caricamento(valore):
    """Altrimenti il caricamento riesce, la cartella della run si crea e la prima chiamata
    muore con un messaggio fuorviante («LLM irraggiungibile»): prima si valida, poi si crea."""
    dati = _config()
    dati["models"]["solo_extra"]["extra_body"] = {"parametro": valore}

    with pytest.raises(MalformedRegistry, match="JSON"):
        ModelRegistry(dati)


def test_x9_un_extra_body_valido_con_valori_annidati_passa(registro):
    dati = _config()
    dati["models"]["solo_extra"]["extra_body"] = {"a": {"b": [1, 2.5, "x", None, True]}}

    assert ModelRegistry(dati).extra_body_for("solo_extra") == {"a": {"b": [1, 2.5, "x", None, True]}}


def test_p8_vede_le_immagini_chi_dovra_fare_critico_o_giudice(reale):
    """Critico su screenshot e giudice hanno bisogno della visione; DeepSeek V4 Pro non ce l'ha (D38), V4.1 Flash si' (D47)."""
    for modello in ("opus-5-5", "gpt-6-1-sol", "glm-5-3-flash", "gemini-4-argon", "gemini-3-8-flash",
                    "deepseek-v4-1-flash"):
        assert "vision_input" in reale.models[modello]["capabilities"], modello
    assert "vision_input" not in reale.models["deepseek-v4-pro"]["capabilities"]
