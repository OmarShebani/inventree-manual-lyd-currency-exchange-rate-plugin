import importlib.util
import os
import sys
import types
from decimal import Decimal
from pathlib import Path

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate


def view(owner):
    return owner.setup_urls()[0].callback


def request(owner, method="get", data=None, superuser=True, authenticated=True):
    factory = APIRequestFactory()
    req = getattr(factory, method)("/configuration/", data=data, format="json")
    if authenticated:
        force_authenticate(
            req,
            user=types.SimpleNamespace(
                is_authenticated=True, is_superuser=superuser, is_staff=superuser
            ),
        )
    return view(owner)(req)


def test_defaults_and_native_api_permission(owner):
    assert request(owner, authenticated=False).status_code in (401, 403)
    assert request(owner, superuser=False).status_code == 403
    response = request(owner)
    assert response.status_code == 200
    assert response.data["config"]["rows"]["USD"]["value"] == "10"
    assert response.data["config"]["global_currency"] == "USD"
    for method in ["put", "post"]:
        assert request(owner, method, {}, superuser=False).status_code == 403
        assert request(owner, method, {}, authenticated=False).status_code in (401, 403)


def test_save_persists_and_conflicts_preserve_other_metadata(owner):
    data = owner.payload()
    config = data["config"]
    config["rows"]["USD"]["value"] = "12"
    body = {"revision": 0, "config": config}
    response = request(owner, "put", body)
    assert response.status_code == 200
    assert response.data["revision"] == 1
    assert owner.payload()["config"]["rows"]["USD"]["value"] == "12"
    assert owner._record().metadata["unrelated"] == {"preserve": True}
    assert request(owner, "put", body).status_code == 409
    assert owner.payload()["revision"] == 1


def test_validation_before_persistence(owner):
    data = owner.payload()
    data["config"]["rows"]["USD"]["value"] = "NaN"
    response = request(owner, "put", {"revision": 0, "config": data["config"]})
    assert response.status_code == 400
    assert owner.payload()["revision"] == 0
    assert request(owner, "put", []).status_code == 400


def test_refresh_snapshot_and_failure_keep_whole_vector(owner, online_provider):
    provider, calls = online_provider
    rates = owner.update_exchange_rates("USD", ["USD", "LYD", "EUR"])
    assert rates["LYD"] == Decimal("10")
    assert rates["EUR"] == Decimal("0.8")
    assert all("LYD" not in symbols and base != "LYD" for base, symbols in calls)
    state = owner.payload()
    assert state["snapshot"] and state["error"] is None
    config = state["config"]
    config["rows"]["USD"]["value"] = "20"
    owner.save_config({"revision": state["revision"], "config": config})
    provider.update_exchange_rates = lambda *args: {}
    fallback = owner.update_exchange_rates("USD", ["USD", "LYD", "EUR"])
    assert fallback == rates
    state2 = owner.payload()
    assert state2["error"]
    assert state2["snapshot"]["at"] == state["snapshot"]["at"]
    assert state2["snapshot"]["revision"] != state2["revision"]
    # The previous vector is safely rebased if the system's default changes.
    assert owner.update_exchange_rates("LYD", ["USD", "LYD", "EUR"])["USD"] == Decimal("0.1")


def test_incomplete_online_response_does_not_replace_rates(owner, online_provider):
    provider, _ = online_provider
    provider.update_exchange_rates = lambda *args: {"USD": 1}
    assert owner.update_exchange_rates("USD", ["USD", "LYD", "EUR"]) == {}
    assert owner.payload()["error"]
    assert owner.payload()["snapshot"] is None


def test_enable_uses_native_settings_and_preserves_codes(owner, host_settings):
    owner.enable_provider(types.SimpleNamespace(is_staff=True, is_superuser=True))
    assert host_settings["CURRENCY_UPDATE_PLUGIN"] == owner.SLUG
    assert set(host_settings["CURRENCY_CODES"].split(",")) >= {"USD", "EUR", "GBP", "CNY", "LYD"}
    assert request(owner, "post", {"action": "bad"}).status_code == 400


def test_refresh_cannot_run_unselected_plugin(owner):
    # refresh imports the host backend before checking selection.
    from unittest.mock import patch

    with patch.dict(
        sys.modules, {"InvenTree.exchange": types.SimpleNamespace(InvenTreeExchange=object)}
    ):
        assert request(owner, "post", {"action": "refresh"}).status_code == 400


def test_two_plugins_have_separate_persistent_settings(host_settings):
    from conftest import PluginRecord
    from inventree_lyd_global.plugin import GlobalLYDExchange
    from inventree_lyd_individual.plugin import IndividualLYDExchange

    first, second = IndividualLYDExchange(), GlobalLYDExchange()
    for plugin in [first, second]:
        PluginRecord.objects.create(key=plugin.SLUG)
    config = first.payload()["config"]
    config["rows"]["USD"]["value"] = "15"
    first.save_config({"revision": 0, "config": config})
    assert second.payload()["config"]["rows"]["USD"]["value"] == "10"


def test_real_inventree_backend(owner, online_provider, host_settings, monkeypatch):
    """Use exact InvenTree 1.5.2 backend against real Django-money database tables."""
    checkout = os.environ.get("INVENTREE_SOURCE")
    if not checkout:
        pytest.skip("Set INVENTREE_SOURCE to exercise native InvenTree backend")
    source = Path(checkout) / "src/backend/InvenTree/InvenTree/exchange.py"
    spec = importlib.util.spec_from_file_location("InvenTree.exchange", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setitem(sys.modules, "InvenTree.exchange", module)
    import plugin

    provider, _ = online_provider
    monkeypatch.setattr(
        plugin.registry,
        "get_plugin",
        lambda slug, **kwargs: owner if slug == owner.SLUG else provider,
    )
    host_settings["CURRENCY_UPDATE_PLUGIN"] = owner.SLUG
    host_settings["CURRENCY_CODES"] += ",LYD"
    from djmoney.contrib.exchange.models import Rate

    result = request(owner, "post", {"action": "refresh"})
    assert result.status_code == 200
    assert Rate.objects.get(currency="LYD").value == Decimal("10")
    assert Rate.objects.get(currency="EUR").value == Decimal("0.8")
    provider.update_exchange_rates = lambda *args: {}
    result = request(owner, "post", {"action": "refresh"})
    assert result.data["error"]
    assert Rate.objects.get(currency="LYD").value == Decimal("10")
    assert Rate.objects.count() == 5


def test_session_writes_require_csrf(owner):
    factory = APIRequestFactory(enforce_csrf_checks=True)
    req = factory.put(
        "/configuration/", {"revision": 0, "config": owner.payload()["config"]}, format="json"
    )
    req.user = types.SimpleNamespace(
        is_authenticated=True, is_active=True, is_superuser=True, is_staff=True
    )
    assert view(owner)(req).status_code == 403
