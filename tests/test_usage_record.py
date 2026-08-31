"""Invarianti del record prima che venga passato al listino o serializzato."""

import math

import pytest

from accounting.errors import InvalidUsage
from accounting.record import UsageRecord


@pytest.mark.parametrize("quantity", [-1, math.inf, math.nan, "10"])
def test_rifiuta_quantita_non_fatturabili(quantity):
    with pytest.raises(InvalidUsage):
        UsageRecord(model="m", quantities={"input_tokens": quantity})


def test_rifiuta_measurement_source_sconosciuto():
    with pytest.raises(InvalidUsage):
        UsageRecord(model="m", quantities={}, measurement_source="inventato")
