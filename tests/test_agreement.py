"""Gli accordi di R1.10 seguono la regola fissata prima dei voti (PROTOCOLLO §6).

Nota di design (tesi):
    Qui ci sono solo voti finti, costruiti nel test: la regola di accettazione
    del giudice e' stata registrata prima di guardare i voti veri e questi test
    la traducono in codice senza mai leggere `campaigns/data/`. I valori attesi
    di Scott's pi e dell'alfa ordinale sono calcolati a mano nei commenti.
"""

import math
import random

import pytest

from agreement import (
    BOOTSTRAP_SAMPLES,
    BOOTSTRAP_SEED,
    DELTA_MARGIN,
    AgreementError,
    accept,
    agreement_report,
    krippendorff_alpha_ordinal,
    pairwise_mean,
    percent_agreement,
    ratings_from,
    scott_pi,
    sign,
)
from calibration import Vote
from judge import Judgment
from task_model import CampaignError


def _j(pair_id: str, value: float | None) -> Judgment:
    return Judgment(item="v-" + pair_id, pair_id=pair_id, value=value, forward=None, backward=None, attempts=2,
                    seconds=1.0, usage={}, date="2026-10-25T00:00:00+00:00", meta={})


def _votes(voter: str, values: dict[str, int], repeats: dict[str, int] | None = None) -> list[Vote]:
    out = [Vote(voter, pair, value, False, 1000) for pair, value in values.items()]
    out += [Vote(voter, pair, value, True, 1000) for pair, value in (repeats or {}).items()]
    return out


# --- misure di base ----------------------------------------------------------

def test_constants_are_those_of_the_protocol():
    assert DELTA_MARGIN == -0.10
    assert BOOTSTRAP_SAMPLES == 10_000
    assert BOOTSTRAP_SEED == 20261025


@pytest.mark.parametrize("value,expected", [(-2, -1), (-0.5, -1), (0, 0), (0.0, 0), (0.5, 1), (2, 1)])
def test_sign(value, expected):
    assert sign(value) == expected


def test_scott_pi_by_hand():
    # po = 3/4; categorie dei due votanti insieme: +1 tre volte, 0 tre, -1 due su 8
    # pe = 0,375^2 + 0,375^2 + 0,25^2 = 0,34375; pi = (0,75 - 0,34375) / 0,65625
    assert scott_pi([1, 1, 0, -1], [1, 0, 0, -1]) == pytest.approx(0.40625 / 0.65625)


def test_scott_pi_perfect_and_symmetric():
    a, b = [1, 0, -1, 1, 1], [1, -1, -1, 0, 1]
    assert scott_pi(a, a) == pytest.approx(1.0)
    assert scott_pi(a, b) == pytest.approx(scott_pi(b, a))


def test_scott_pi_can_be_negative():
    assert scott_pi([1, -1, 1, -1], [-1, 1, -1, 1]) < 0


def test_scott_pi_undefined_raises():
    with pytest.raises(AgreementError):
        scott_pi([1, 1, 1], [1, 1, 1])
    with pytest.raises(AgreementError):
        scott_pi([1, 0], [1])
    with pytest.raises(AgreementError):
        scott_pi([], [])


def test_agreement_error_is_a_campaign_error():
    assert issubclass(AgreementError, CampaignError)


def test_percent_agreement():
    assert percent_agreement([1, 0, -1, 1], [1, 1, -1, 0]) == pytest.approx(0.5)


def test_alpha_ordinal_by_hand():
    # unita' (1,1), (2,2), (1,2): o11 = o22 = 2, o12 = o21 = 1, n1 = n2 = 3, n = 6
    # delta^2(1,2) = (n1 + n2 - (n1 + n2)/2)^2 = 9; Do = 18/6 = 3; De = 2*3*3*9/30 = 5,4
    assert krippendorff_alpha_ordinal([1, 2, 1], [1, 2, 2]) == pytest.approx(1 - 3 / 5.4)


def test_alpha_ordinal_uses_only_the_order():
    a = [-2, -1, 0, 1, 2, 1, 0]
    b = [-2, -1, 1, 1, 2, 0, 0]
    stretched = [x * 10 if x > 0 else x for x in b]
    stretched_a = [x * 10 if x > 0 else x for x in a]
    assert krippendorff_alpha_ordinal(a, b) == pytest.approx(krippendorff_alpha_ordinal(stretched_a, stretched))


def test_alpha_ordinal_far_disagreement_costs_more():
    base = [-2, -1, 0, 1, 2] * 4
    near = list(base)
    near[0] = -1     # -2 contro -1: vicini
    far = list(base)
    far[0] = 2       # -2 contro +2: opposti
    assert krippendorff_alpha_ordinal(base, near) > krippendorff_alpha_ordinal(base, far)
    assert krippendorff_alpha_ordinal(base, base) == pytest.approx(1.0)


def test_alpha_accepts_half_points():
    assert -1 <= krippendorff_alpha_ordinal([-1.5, 0.5, 2, 0], [-2, 1, 2, 0]) <= 1


# --- dai voti alle valutazioni -----------------------------------------------

def test_ratings_drop_repeats_and_unratable_pairs():
    votes = _votes("u1", {"c1": 2, "c2": -1, "c3": 0}, repeats={"c1": -2}) + _votes("u2", {"c1": 1, "c3": 1})
    judgments = [_j("c1", 1.5), _j("c2", None), _j("c3", -0.5)]
    humans, judge = ratings_from(votes, judgments)
    assert humans == {"u1": {"c1": 2, "c3": 0}, "u2": {"c1": 1, "c3": 1}}
    assert judge == {"c1": 1.5, "c3": -0.5}


def test_double_first_vote_is_an_error():
    votes = _votes("u1", {"c1": 2}) + _votes("u1", {"c1": 1})
    with pytest.raises(AgreementError):
        ratings_from(votes, [_j("c1", 1.0)])


def test_pairwise_mean_uses_common_pairs_only():
    signs = {"u1": {"a": 1, "b": -1, "c": 0, "d": 1},
             "u2": {"a": 1, "b": -1, "c": 0, "d": -1},
             "u3": {"a": 1, "b": -1}}
    # u1-u2 su a,b,c,d; u1-u3 e u2-u3 su a,b soltanto (accordo perfetto: pi = 1)
    expected = (scott_pi([1, -1, 0, 1], [1, -1, 0, -1]) + 1 + 1) / 3
    assert pairwise_mean(signs, scott_pi, items=["a", "b", "c", "d"]) == pytest.approx(expected)


def test_pairwise_mean_follows_the_items_list_with_duplicates():
    signs = {"u1": {"a": 1, "b": -1, "c": 1}, "u2": {"a": 1, "b": 1, "c": 1}}
    # ripescaggio del bootstrap: "a" due volte, "c" esclusa
    assert pairwise_mean(signs, percent_agreement, items=["a", "a", "b"]) == pytest.approx(2 / 3)


# --- regola di accettazione ---------------------------------------------------

@pytest.mark.parametrize("hh_low,jh_low,delta_low,expected", [
    (0.05, 0.02, -0.09, True),
    (0.05, 0.02, -0.10, False),   # sul margine non basta: deve stare sopra
    (0.00, 0.02, 0.05, False),    # umani non sopra il caso
    (0.05, 0.00, 0.05, False),    # giudice non sopra il caso
    (0.30, 0.40, 0.10, True),     # il giudice puo' superare gli umani
])
def test_accept(hh_low, jh_low, delta_low, expected):
    assert accept(hh_low, jh_low, delta_low) is expected


# --- rapporto completo --------------------------------------------------------

def _simulated(n_pairs=60, n_voters=4, judge_noise=0.6, seed=7):
    rng = random.Random(seed)
    grade = lambda x: max(-2, min(2, round(x)))  # noqa: E731
    truth = {f"c{i:03d}": rng.gauss(0, 1.2) for i in range(n_pairs)}
    votes = []
    for v in range(n_voters):
        votes += _votes(f"u{v}", {p: grade(t + rng.gauss(0, 0.8)) for p, t in truth.items()})
    judgments = [_j(p, (grade(t + rng.gauss(0, judge_noise)) + grade(t + rng.gauss(0, judge_noise))) / 2)
                 for p, t in truth.items()]
    return votes, judgments


def test_report_has_point_estimates_and_intervals():
    votes, judgments = _simulated()
    report = agreement_report(votes, judgments, samples=300, seed=1)
    for name in ("pi_hh", "pi_jh", "delta", "acc_hh", "acc_jh", "acc_hh_no_ties", "acc_jh_no_ties",
                 "alpha_hh", "alpha_jh"):
        low, point, high = report[name]["low"], report[name]["point"], report[name]["high"]
        assert low <= high and not math.isnan(point)
    assert report["delta"]["point"] == pytest.approx(report["pi_jh"]["point"] - report["pi_hh"]["point"])
    assert report["pairs"] == 60 and report["voters"] == 4 and report["unratable"] == 0
    assert report["accepted"] is accept(report["pi_hh"]["low"], report["pi_jh"]["low"], report["delta"]["low"])


def test_report_is_reproducible_with_the_seed():
    votes, judgments = _simulated()
    assert agreement_report(votes, judgments, samples=200, seed=3) == agreement_report(votes, judgments,
                                                                                         samples=200, seed=3)


def test_unratable_pairs_leave_every_measure_and_are_counted():
    votes, judgments = _simulated()
    judgments[0] = _j(judgments[0].pair_id, None)
    report = agreement_report(votes, judgments, samples=100, seed=1)
    assert report["pairs"] == 59 and report["unratable"] == 1


def test_a_good_judge_passes_and_a_random_one_fails():
    votes, judgments = _simulated(n_pairs=150, n_voters=6, judge_noise=0.5)
    assert agreement_report(votes, judgments, samples=400, seed=2)["accepted"] is True
    rng = random.Random(5)
    noise = [_j(j.pair_id, float(rng.choice([-2, -1, 0, 1, 2]))) for j in judgments]
    assert agreement_report(votes, noise, samples=400, seed=2)["accepted"] is False


def test_judgment_without_votes_is_an_error():
    votes, judgments = _simulated(n_pairs=10)
    with pytest.raises(AgreementError):
        agreement_report(votes, judgments + [_j("zzz", 1.0)], samples=10, seed=1)


def test_voted_pair_without_judgment_is_an_error():
    # «non valutabile» e' un giudizio con valore None; un giudizio assente e' un lotto incompleto
    votes, judgments = _simulated(n_pairs=10)
    with pytest.raises(AgreementError):
        agreement_report(votes, judgments[1:], samples=10, seed=1)


def test_too_few_voters_is_an_error():
    votes, judgments = _simulated(n_voters=1)
    with pytest.raises(AgreementError):
        agreement_report(votes, judgments, samples=10, seed=1)
