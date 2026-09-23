"""Real Django/DRF and currency models; small adapters stand in for the InvenTree host.

Set INVENTREE_SOURCE to an InvenTree checkout to additionally exercise its actual
exchange backend (see test_runtime.py). No production database is accessed.
"""

import logging
import sys
import types
from copy import deepcopy

import django
import pytest
from django.conf import settings

settings.configure(
    SECRET_KEY="tests-only",
    USE_TZ=True,
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    INSTALLED_APPS=[
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "djmoney.contrib.exchange",
    ],
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"]
    },
    ROOT_URLCONF=__name__,
)
django.setup()

from django.db import connection, models  # noqa: E402
from rest_framework.permissions import BasePermission  # noqa: E402

urlpatterns = []


class PluginRecord(models.Model):
    key = models.CharField(max_length=100, unique=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        app_label = "tests"

    def get_metadata(self, key):
        return deepcopy(self.metadata.get(key))

    def set_metadata(self, key, data):
        self.metadata[key] = deepcopy(data)
        self.save()


class SuperuserPermission(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


class HostPlugin:
    @property
    def name(self):
        return self.NAME


class CurrencyMixin:
    pass


class UrlMixin:
    pass


host = types.ModuleType("plugin")
host.InvenTreePlugin = HostPlugin
host.registry = types.SimpleNamespace(get_plugin=lambda *args, **kwargs: None)
host.PluginMixinEnum = types.SimpleNamespace(CURRENCY_EXCHANGE="currency")
sys.modules["plugin"] = host
sys.modules["plugin.models"] = types.SimpleNamespace(PluginConfig=PluginRecord)
sys.modules["plugin.mixins"] = types.SimpleNamespace(
    CurrencyExchangeMixin=CurrencyMixin, UrlsMixin=UrlMixin
)
sys.modules["InvenTree"] = types.ModuleType("InvenTree")
sys.modules["InvenTree.permissions"] = types.SimpleNamespace(
    IsSuperuserOrSuperScope=SuperuserPermission
)
sys.modules["common"] = types.ModuleType("common")
sys.modules["structlog"] = types.SimpleNamespace(get_logger=logging.getLogger)


@pytest.fixture(autouse=True)
def database():
    from djmoney.contrib.exchange.models import ExchangeBackend, Rate

    with connection.schema_editor() as schema:
        for model in [PluginRecord, ExchangeBackend, Rate]:
            schema.create_model(model)
    yield
    with connection.schema_editor() as schema:
        for model in [Rate, ExchangeBackend, PluginRecord]:
            schema.delete_model(model)


@pytest.fixture
def host_settings(monkeypatch):
    config = {
        "CURRENCY_UPDATE_PLUGIN": "",
        "CURRENCY_CODES": "USD,EUR,GBP,CNY",
        "INVENTREE_DEFAULT_CURRENCY": "USD",
    }
    currency = types.SimpleNamespace(
        currency_codes=lambda: config["CURRENCY_CODES"].split(","),
        currency_code_default=lambda: config["INVENTREE_DEFAULT_CURRENCY"],
    )
    setting = types.SimpleNamespace(
        get_global_setting=lambda key, **kwargs: config.get(key),
        set_global_setting=lambda key, value, **kwargs: config.update({key: value}),
    )
    monkeypatch.setitem(sys.modules, "common.currency", currency)
    monkeypatch.setitem(sys.modules, "common.settings", setting)
    return config


@pytest.fixture(params=["individual", "global"])
def owner(request, host_settings):
    from inventree_lyd_global.plugin import GlobalLYDExchange
    from inventree_lyd_individual.plugin import IndividualLYDExchange

    cls = IndividualLYDExchange if request.param == "individual" else GlobalLYDExchange
    instance = cls()
    PluginRecord.objects.create(key=instance.SLUG, metadata={"unrelated": {"preserve": True}})
    return instance


@pytest.fixture
def online_provider(monkeypatch):
    calls = []
    online = {"USD": 1, "EUR": 0.8, "GBP": 0.5, "CNY": 7, "JPY": 150}

    def update(base, symbols):
        calls.append((base, symbols))
        return {c: online[c] / online[base] for c in set(symbols) | {base} if c in online}

    provider = types.SimpleNamespace(update_exchange_rates=update)
    monkeypatch.setattr(
        host.registry,
        "get_plugin",
        lambda slug, **kwargs: provider if slug == "inventreecurrencyexchange" else None,
    )
    return provider, calls
