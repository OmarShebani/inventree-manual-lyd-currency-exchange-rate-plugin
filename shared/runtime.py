"""InvenTree integration using the native provider, metadata, and REST authentication."""

import copy
import logging

from django.db import transaction
from django.urls import path, reverse
from django.utils.timezone import now
from InvenTree.permissions import IsSuperuserOrSuperScope
from moneyed import CURRENCIES
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .engine import ConfigurationError, calculate, defaults, online_currencies, rebase, validate

logger = logging.getLogger(__name__)
STATE_KEY = "lyd_exchange_v1"


class Conflict(APIException):
    status_code = 409
    default_detail = "Settings changed in another session. Reload before saving."


class LYDRuntime:
    """Shared implementation; concrete classes define distinct identities and variants."""

    ADMIN_SOURCE = "settings.js"
    MIN_VERSION = "1.5.2"
    MAX_VERSION = "1.5.99"
    VERSION = "0.1.0"
    WEBSITE = "https://github.com/blank404-sh/inventree-manual-lyd-currency-exchange-rate-plugin"
    AUTHOR = "Omar Shebani"

    def _record(self, lock=False):
        from plugin.models import PluginConfig

        query = PluginConfig.objects
        if lock:
            query = query.select_for_update()
        return query.get(key=self.SLUG)

    def _state(self, record):
        return copy.deepcopy(
            record.get_metadata(STATE_KEY)
            or {
                "revision": 0,
                "config": defaults(self.INDIVIDUAL),
                "snapshot": None,
                "last_attempt": None,
                "error": None,
            }
        )

    def _config(self, state):
        return validate(state["config"], self.INDIVIDUAL, CURRENCIES)

    def _fetch(self, config, targets):
        from plugin import registry

        needed = online_currencies(config, targets)
        online = {}
        if needed:
            provider = registry.get_plugin("inventreecurrencyexchange", active=True)
            if not provider:
                raise ConfigurationError("The original InvenTree currency provider is not active.")
            # Request one coherent online table. Never send LYD to Frankfurter.
            base = "USD" if "USD" in needed else sorted(needed)[0]
            online = provider.update_exchange_rates(base, sorted(needed - {base}))
            if not isinstance(online, dict) or not needed.issubset(online):
                raise ConfigurationError(
                    "The original provider returned no complete rate table. Check the network "
                    "and whether it supports every automatic currency/intermediary."
                )
        return calculate(config, targets, online)

    def update_exchange_rates(self, base_currency, symbols):
        """Native CurrencyExchangeMixin callback; never partially replace a rate table."""
        with transaction.atomic():
            record = self._record(lock=True)
            state = self._state(record)
            state["last_attempt"] = now().isoformat()
            try:
                config = self._config(state)
                targets = set(symbols) | {base_currency, "LYD"} | set(config["rows"])
                lyd = self._fetch(config, targets)
                rates = rebase(lyd, base_currency, symbols)
            except Exception as exc:
                logger.exception("LYD exchange refresh failed for %s", self.SLUG)
                state["error"] = str(exc)[:1000] or "Exchange rate update failed."
                record.set_metadata(STATE_KEY, state)
                # Keep the complete previous vector, rebased if the system base changed.
                # Do not mix freshly entered manual values with stale online rates.
                snapshot = state.get("snapshot")
                if snapshot:
                    try:
                        return rebase(snapshot["lyd"], base_currency, symbols)
                    except ConfigurationError:
                        pass
                return {}  # InvenTree preserves its stored rates on an empty result.
            state["snapshot"] = {
                "lyd": {code: str(value) for code, value in lyd.items()},
                "at": state["last_attempt"],
                "revision": state["revision"],
            }
            state["error"] = None
            record.set_metadata(STATE_KEY, state)
            return rates

    def payload(self):
        from common.currency import currency_codes
        from common.settings import get_global_setting

        state = self._state(self._record())
        return {
            **state,
            "individual": self.INDIVIDUAL,
            "title": self.TITLE,
            "currencies": [
                {"code": code, "name": str(c.name)}
                for code, c in sorted(CURRENCIES.items())
                if code != "LYD"
            ],
            "enabled_currencies": currency_codes(),
            "selected": get_global_setting("CURRENCY_UPDATE_PLUGIN") == self.SLUG,
        }

    def save_config(self, data):
        if not isinstance(data, dict) or set(data) != {"revision", "config"}:
            raise ValidationError("Expected config and revision.")
        try:
            config = validate(data["config"], self.INDIVIDUAL, CURRENCIES)
        except ConfigurationError as exc:
            raise ValidationError(str(exc)) from exc
        with transaction.atomic():
            record = self._record(lock=True)
            state = self._state(record)
            if type(data["revision"]) is not int or data["revision"] != state["revision"]:
                raise Conflict()
            state.update(config=config, revision=state["revision"] + 1, error=None)
            record.set_metadata(STATE_KEY, state)
        return self.payload()

    def enable_provider(self, user):
        from common.currency import currency_codes
        from common.settings import get_global_setting, set_global_setting

        config = self._config(self._state(self._record()))
        # Use native settings APIs, preserving all existing supported currencies.
        set_global_setting("CURRENCY_UPDATE_PLUGIN", self.SLUG, change_user=user)
        if get_global_setting("CURRENCY_UPDATE_PLUGIN") != self.SLUG:
            raise ValidationError("Currency provider is overridden by server configuration.")
        codes = list(dict.fromkeys(currency_codes() + ["LYD"] + list(config["rows"])))
        set_global_setting("CURRENCY_CODES", ",".join(codes), change_user=user)
        if not set(codes).issubset(currency_codes()):
            raise ValidationError(
                "Supported currencies are overridden by server configuration. "
                "Add LYD and the configured currencies to INVENTREE_CURRENCY_CODES."
            )

    def refresh(self):
        from common.currency import currency_code_default
        from common.settings import get_global_setting
        from InvenTree.exchange import InvenTreeExchange

        if get_global_setting("CURRENCY_UPDATE_PLUGIN") != self.SLUG:
            raise ValidationError("Select this currency provider before refreshing system rates.")
        # Same native backend used by InvenTree's scheduled exchange-rate task.
        InvenTreeExchange().update_rates(base_currency=currency_code_default())
        return self.payload()

    def get_admin_context(self):
        return {"endpoint": reverse(f"plugin:{self.SLUG}:configuration")}

    def setup_urls(self):
        owner = self

        class ConfigurationView(APIView):
            permission_classes = [IsAuthenticated, IsSuperuserOrSuperScope]
            parser_classes = [JSONParser]

            def get(self, request):
                return Response(owner.payload())

            def put(self, request):
                return Response(owner.save_config(request.data))

            def post(self, request):
                action = request.data.get("action") if isinstance(request.data, dict) else None
                if action == "enable":
                    owner.enable_provider(request.user)
                elif action != "refresh":
                    raise ValidationError("Choose enable or refresh.")
                return Response(owner.refresh())

        return [path("configuration/", ConfigurationView.as_view(), name="configuration")]
