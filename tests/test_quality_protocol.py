"""Il protocollo: un file di dati che l'autore della tesi scrive, e che il codice si limita a leggere."""

from pathlib import Path

import pytest

from quality.protocol import Protocol, load_protocol

PROTOCOLLO = Path("quality/protocol.toml")

MINIMO = """
[state]
template = "{instructions} {solution}"
[question]
text = "ok?"
criteria_true = "si"
criteria_false = "no"
[frontier]
model = "opus-5-5"
system = "s"
user_template = "{instructions} {solution}"
[decision]
primary = "d1_hosted_plain"
reference = "frontier"
promising_lower_bound = 0.70
max_gap_to_reference = 0.10
negative_upper_bound = 0.65
[run]
repetitions_d1 = 3
repetitions_frontier = 1
max_total_usd = 4.0
reserve_per_call_usd = 0.02
workers = 4
bootstrap_samples = 2000
seed = 0
"""


def _scrivi(tmp_path, testo):
    percorso = tmp_path / "p.toml"
    percorso.write_text(testo)
    return percorso


def test_il_protocollo_vero_del_progetto_e_valido_e_ha_le_soglie_di_d21():
    p = load_protocol(PROTOCOLLO)

    assert isinstance(p, Protocol)
    assert (p.promising_lower_bound, p.max_gap_to_reference, p.negative_upper_bound) == (0.70, 0.10, 0.65)
    assert p.primary == "d1_hosted_plain" and p.reference == "frontier"
    assert p.max_total_usd == 4.0 and p.repetitions_frontier == 1 and p.repetitions_d1 == 3


def test_i_campi_si_leggono(tmp_path):
    p = load_protocol(_scrivi(tmp_path, MINIMO))

    assert (p.question, p.criteria) == ("ok?", ("si", "no"))
    assert p.frontier_model == "opus-5-5" and p.workers == 4 and p.bootstrap_samples == 2000


@pytest.mark.parametrize("vecchio, nuovo, messaggio", [
    ("promising_lower_bound = 0.70", "promising_lower_bound = 1.5", "promising_lower_bound"),
    ("negative_upper_bound = 0.65", "negative_upper_bound = 0.95", "negative_upper_bound"),
    ("max_total_usd = 4.0", "max_total_usd = -1", "max_total_usd"),
    ("workers = 4", "workers = 0", "workers"),
    ('template = "{instructions} {solution}"\n[question]', 'template = "{instructions} {label}"\n[question]', "segnaposto"),
    ('primary = "d1_hosted_plain"', 'primary = "inventato"', "primary"),
])
def test_un_protocollo_incoerente_e_un_errore_prima_di_spendere(tmp_path, vecchio, nuovo, messaggio):
    with pytest.raises(ValueError, match=messaggio):
        load_protocol(_scrivi(tmp_path, MINIMO.replace(vecchio, nuovo, 1)))


def test_una_sezione_mancante_e_un_errore_parlante(tmp_path):
    with pytest.raises(ValueError, match="frontier"):
        load_protocol(_scrivi(tmp_path, MINIMO.replace("[frontier]", "[altro]", 1)))
