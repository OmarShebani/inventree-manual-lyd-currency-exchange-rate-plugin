from decimal import Decimal

import pytest
from moneyed import CURRENCIES

from shared.engine import (
    ConfigurationError,
    calculate,
    defaults,
    online_currencies,
    rebase,
    validate,
)

ONLINE = {"USD": "1", "EUR": "0.8", "GBP": "0.5", "CNY": "7", "JPY": "150"}


def manual(value, direction="foreign_to_lyd"):
    return {"mode": "manual", "value": value, "direction": direction}


@pytest.mark.parametrize("individual", [True, False])
def test_default_anchor_and_online_rates(individual):
    config = validate(defaults(individual), individual, CURRENCIES)
    result = calculate(config, ONLINE, ONLINE)
    assert result["USD"] == Decimal("0.1")
    assert result["EUR"] == Decimal("0.08")
    assert result["GBP"] == Decimal("0.05")
    assert result["CNY"] == Decimal("0.7")
    assert result["JPY"] == Decimal("15")
    assert rebase(result, "USD", ONLINE)["EUR"] == Decimal("0.8")
    assert rebase(result, "LYD", ONLINE)["USD"] == Decimal("0.1")
    assert rebase(result, "EUR", ONLINE)["USD"] == Decimal("1.25")


def test_individual_override_changes_cross_rates_and_chains():
    config = defaults(True)
    config["rows"]["EUR"] = manual("20")
    config["rows"]["GBP"] = {"mode": "auto", "via": "EUR"}
    config["rows"]["CNY"] = {"mode": "auto", "via": "GBP"}
    config = validate(config, True, CURRENCIES)
    result = calculate(config, ONLINE, ONLINE)
    assert result["EUR"] == Decimal("0.05")
    assert result["GBP"] == Decimal("0.03125")
    assert result["CNY"] == Decimal("0.4375")
    assert rebase(result, "USD", ONLINE)["EUR"] == Decimal("0.5")
    assert result["JPY"] == Decimal("15")  # Unconfigured: global USD path.


def test_removal_restores_global_and_referenced_currency_still_resolves():
    config = defaults(True)
    config["rows"]["GBP"] = {"mode": "auto", "via": "EUR"}
    del config["rows"]["EUR"]
    config = validate(config, True, CURRENCIES)
    assert calculate(config, ["GBP"], ONLINE)["GBP"] == Decimal("0.05")


def test_global_currency_can_change():
    config = {"global_currency": "EUR", "rows": {"EUR": manual("12")}}
    config = validate(config, False, CURRENCIES)
    rates = calculate(config, ONLINE, ONLINE)
    assert abs(rebase(rates, "USD", ONLINE)["CNY"] - Decimal("7")) < Decimal("1e-25")
    assert rates["EUR"] == Decimal(1) / Decimal(12) or abs(
        rates["EUR"] - Decimal(1) / 12
    ) < Decimal("1e-27")


def test_reciprocal_direction():
    config = defaults(False)
    config["rows"]["USD"] = manual("0.1", "lyd_to_foreign")
    assert calculate(config, ["USD"], {})["USD"] == Decimal("0.1")


@pytest.mark.parametrize(
    "value", ["0", "-2", "NaN", "Infinity", "-Infinity", "", None, True, "1e100", "1e-30"]
)
def test_bad_manual_numbers(value):
    config = defaults(False)
    config["rows"]["USD"]["value"] = value
    with pytest.raises(ConfigurationError):
        validate(config, False, CURRENCIES)


@pytest.mark.parametrize(
    "chain", [("EUR", "EUR"), ("EUR", "GBP", "EUR"), ("EUR", "GBP", "CNY", "EUR")]
)
def test_cycles(chain):
    config = defaults(True)
    for source, via in zip(chain, chain[1:]):
        config["rows"][source] = {"mode": "auto", "via": via}
    with pytest.raises(ConfigurationError, match="Circular"):
        validate(config, True, CURRENCIES)


def test_global_must_remain_manual_and_present():
    for row in [None, {"mode": "auto", "via": "EUR"}]:
        config = defaults(True)
        if row is None:
            del config["rows"]["USD"]
        else:
            config["rows"]["USD"] = row
        with pytest.raises(ConfigurationError, match="global intermediary"):
            validate(config, True, CURRENCIES)


def test_global_plugin_rejects_extra_rows():
    with pytest.raises(ConfigurationError, match="only the global"):
        validate(defaults(True), False, CURRENCIES)


def test_unsupported_online_currency_fails_but_manual_is_supported():
    config = defaults(True)
    config["rows"]["TND"] = manual("3")
    validate(config, True, CURRENCIES)
    needed = online_currencies(config, ["TND", "CNY"])
    assert needed == {"USD", "CNY"}
    assert calculate(config, ["TND"], {})["TND"] > 0
    with pytest.raises(ConfigurationError, match="no rate"):
        calculate(defaults(False), ["TND"], ONLINE)


def test_no_lyd_request_and_transitive_online_dependencies():
    config = defaults(True)
    config["rows"]["CNY"]["via"] = "GBP"
    assert online_currencies(config, ["LYD", "CNY"]) == {"CNY", "GBP", "USD"}


def test_rebase_rejects_incomplete_snapshot_and_storage_underflow():
    with pytest.raises(ConfigurationError, match="complete"):
        rebase({"USD": "0.1"}, "USD", ["EUR"])
    with pytest.raises(ConfigurationError, match="precision"):
        rebase({"USD": "1", "EUR": "0.00000001"}, "USD", ["EUR"])


@pytest.mark.parametrize("base", list(ONLINE))
def test_global_foreign_cross_rates_preserved_for_every_base(base):
    rates = calculate(defaults(False), ONLINE, ONLINE)
    result = rebase(rates, base, ONLINE)
    for code in ONLINE:
        expected = Decimal(ONLINE[code]) / Decimal(ONLINE[base])
        assert abs(result[code] - expected) < Decimal("1e-25")
