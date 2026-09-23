"""Individual LYD override provider."""

from plugin import InvenTreePlugin
from plugin.mixins import CurrencyExchangeMixin, UrlsMixin

from .runtime import LYDRuntime


class IndividualLYDExchange(LYDRuntime, CurrencyExchangeMixin, UrlsMixin, InvenTreePlugin):
    NAME = "IndividualLYDExchange"
    SLUG = "lyd-individual-exchange"
    TITLE = "LYD Exchange Rates — Individual Overrides"
    DESCRIPTION = "Manual LYD rates and per-currency intermediaries; derives all cross-rates."
    INDIVIDUAL = True
