# LYD exchange-rate plugins for InvenTree

Two **independently installable** plugins for **InvenTree 1.5.2**. Both start with
**USD as the required manual global intermediary: 1 USD = 10 LYD**. This is the
requested starting value, not an online market rate.

| Plugin | Individual Overrides | Global Only |
| --- | --- | --- |
| Source | `plugins/individual/` | `plugins/global/` |
| Package | `inventree-lyd-individual-exchange` | `inventree-lyd-global-exchange` |
| Manual global LYD rate, reversible entry direction | Yes | Yes |
| Separate manual LYD rates for other currencies | Yes | No |
| Choose an intermediary for each configured currency | Yes | No |
| Add/remove individual currency rows | Yes | No — manage supported currencies in InvenTree |
| Preserve online foreign-to-foreign cross-rates | Only when overrides agree with online rates | Yes, within InvenTree's storage precision |

Install either or both. **Only one can be selected as InvenTree's Currency Update
Plugin at a time.** Their configuration and last-valid rate snapshots are separate.

## Individual Overrides

USD, GBP, EUR, and CNY are initially configured. USD is manual at 10 LYD; the other
three initially calculate through USD. Each non-global row can be manual or
calculate LYD → selected intermediary → that currency. Chains of intermediaries
are allowed if they end at a manual rate. Circular chains are rejected.

Currencies without an individual row calculate through the global intermediary.
Removing a row restores that behavior and does not delete the currency from
InvenTree. The global row cannot be removed or made automatic. Choose a new
global currency and give it a manual rate before saving.

**InvenTree uses a single connected rate table.** For example, manually setting
1 USD = 10 LYD and 1 EUR = 20 LYD also makes 1 EUR = 2 USD throughout InvenTree.
The settings page displays this consequence explicitly.

## Global Only

One required manually entered LYD rate anchors all conversions. You can change
the global currency and switch between entering `1 USD = X LYD` and
`1 LYD = X USD`. With 1 USD = 10 LYD and an online rate of 1 EUR = 1.10 USD,
this plugin calculates 1 EUR = 11 LYD. Other foreign cross-rates follow the
original provider. Add/remove supported currencies using native Pricing settings.

## InvenTree integration

- Uses native `CurrencyExchangeMixin` and the **existing active
  InvenTreeCurrencyExchange plugin** to obtain online rates. No new exchange API,
  API key, monkey patches, custom pricing code, or core-source edits.
- Dedicated custom settings panel: **Settings → Admin Center → Plugins → select
  the plugin → Plugin Configuration**. Only superusers can read or change its
  configuration endpoints. Uses InvenTree's authenticated API client and DRF.
- **Use this provider and enable currencies** selects the plugin and adds LYD
  plus configured currency rows to Supported Currencies via native settings APIs.
  It preserves previously enabled currencies.
- Configuration lives in `PluginConfig` metadata under `lyd_exchange_v1`.
  This avoids the 2,000-character limit of standard plugin setting values.
- Updates use the native exchange backend and normal currency update schedule.
  Save-and-refresh applies changes immediately if this provider is selected.
- Decimal arithmetic; positive finite input validation; optimistic revision
  checks prevent one settings session from silently overwriting another.
- Failed updates retain the last **complete** successful table, show an error,
  and keep the last-success timestamp. New manual values are not mixed with
  failed online results. If no complete snapshot covers the requested currencies,
  the plugin returns no rates, leaving the stored system rates unchanged.

LYD is already recognized by InvenTree's underlying currency library, but is not
in the default enabled list. The original Frankfurter v1 provider **does not
supply LYD**, so the global LYD rate is always manual. Automatic paths require
both foreign currencies to be supported by the original provider. The individual
plugin can also store manual rates for recognized currencies the provider lacks.
InvenTree stores exchange rates to six decimal places; unrepresentable results
are rejected instead of storing zero.

## Installation and builds

**A ZIP of the repository is not a plugin upload.** Use one of the two wheel
packages, a source package installed with pip, or an appropriate GitHub
subdirectory. See [Docker installation instructions](docs/INSTALL.md).

```sh
python -m pip install -r requirements-dev.txt
python tools/sync_shared.py
python -m build --outdir dist plugins/individual
python -m build --outdir dist plugins/global
```

Each wheel is self-contained and has a distinct Python package and plugin slug.
There is no shared runtime package to install and uninstalling one does not
remove files used by the other.

## Development and verification

Edit common logic in `shared/`, then run `python tools/sync_shared.py` to copy it
into both packages. The generated copies are checked in so each subdirectory is
installable directly from GitHub. CI/tests check they have not drifted.

```sh
python -m pytest
ruff check shared plugins tools tests
# Optional: exercise the exact host backend from an InvenTree checkout:
INVENTREE_SOURCE=/path/to/InvenTree python -m pytest
```

Tests cover rate math, independent settings, validation, permission enforcement,
conflicting saves, stale-rate recovery, and native backend persistence. Host
services are simulated using real Django/DRF and django-money models; the optional
backend tests load InvenTree's real exchange backend. This is not a full Docker
or PostgreSQL deployment test. Validate installation on a test instance before
using it for live pricing.

Browser smoke tests use `node tests/ui.mjs` with Playwright installed. They render
the actual shipped JavaScript against a simulated InvenTree API context.

## Upstream references

- [InvenTree 1.5.2 exchange backend](https://github.com/inventree/InvenTree/blob/1.5.2/src/backend/InvenTree/InvenTree/exchange.py)
- [Original online provider](https://github.com/inventree/InvenTree/blob/1.5.2/src/backend/InvenTree/plugin/builtin/integration/currency_exchange.py)
- [Frankfurter v1 currency list](https://api.frankfurter.dev/v1/currencies)
- [Plugin installation](https://docs.inventree.org/en/1.5.x/plugins/install/)
