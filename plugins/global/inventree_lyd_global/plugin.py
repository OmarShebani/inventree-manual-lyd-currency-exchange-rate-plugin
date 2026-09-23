"""Single manual LYD anchor, preserving online foreign cross-rates."""

from plugin import InvenTreePlugin
from plugin.mixins import CurrencyExchangeMixin, UrlsMixin

from .runtime import LYDRuntime


class GlobalLYDExchange(LYDRuntime, CurrencyExchangeMixin, UrlsMixin, InvenTreePlugin):
    NAME = "GlobalLYDExchange"
    SLUG = "lyd-global-exchange"
    TITLE = "LYD Exchange Rates — Global Only"
    DESCRIPTION = "One manual LYD anchor; all other currencies follow the original online provider."
    INDIVIDUAL = False
