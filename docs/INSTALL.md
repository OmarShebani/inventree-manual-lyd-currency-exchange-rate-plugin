# Install either LYD plugin on InvenTree 1.5.2 (Docker)

A ZIP is only a source archive. InvenTree does not install this plugin by uploading
that ZIP. Install the Python package in the container environment, restart,
activate it, and select it as the currency provider.

## 1. Choose a package

| Choice | Wheel |
| --- | --- |
| Individual manual overrides and intermediary rows | `inventree_lyd_individual_exchange-0.1.0-py3-none-any.whl` |
| One manual global rate, online foreign cross-rates | `inventree_lyd_global_exchange-0.1.0-py3-none-any.whl` |

The built wheels are in `dist/`. You can install both, but only the selected
provider controls InvenTree's rates. Both start with **1 USD = 10 LYD**.

## 2. Install persistently from a wheel

Copy your chosen wheel (or both) to an `extensions/` directory in the persistent
InvenTree data volume. Both the server and worker must be able to see it.

Add the appropriate line(s) to your **existing** `plugins.txt`, next to InvenTree's
configuration file. For the standard `/home/inventree/data` container mount:

```text
/home/inventree/data/extensions/inventree_lyd_individual_exchange-0.1.0-py3-none-any.whl
/home/inventree/data/extensions/inventree_lyd_global_exchange-0.1.0-py3-none-any.whl
```

Keep just the relevant line if installing only one. Paths in `plugins.txt` must
be container paths, not paths on your workstation.

Ensure plugin support is enabled in the server configuration:
`INVENTREE_PLUGINS_ENABLED=true`. Enable **Check Plugins on Startup** so recreated
containers reinstall the packages. Keep the wheel files on the persistent volume.

For standard Compose service names, run from the directory containing your
InvenTree Compose file:

```sh
docker compose exec inventree-server invoke plugins
docker compose restart inventree-server inventree-worker
```

Adapt service names and mounted paths to your deployment. Do not run these from
this plugin repository unless your InvenTree Compose file is actually here.

## 3. Activate and configure

1. Sign in as an InvenTree superuser.
2. Go to **Settings → Admin Center → Plugins**, then activate the installed
   **LYD Exchange Rates — Individual Overrides** and/or **LYD Exchange Rates —
   Global Only** plugin.
3. Enable **URL integration** in InvenTree's plugin settings
   (`ENABLE_PLUGINS_URL`). Restart the server and worker after activation.
4. Open the chosen plugin, then expand **Plugin Configuration**. This is its
   dedicated LYD settings panel.
5. Adjust rates if needed. The global intermediary is required and always manual.
6. Click **Use this provider and enable currencies**. This saves your settings,
   selects that provider, adds LYD and its configured rows to Supported Currencies,
   and refreshes the native exchange-rate table.
7. Check the last-success timestamp and rate preview. Errors remain visible and
   preserve the previous complete table. A failed initial refresh means the new
   configuration has not yet been applied.

The mandatory original **InvenTreeCurrencyExchange** plugin remains active. These
plugins call it for online rates; do not attempt to uninstall or disable it.
Native **Currency Update Interval** controls subsequent automatic refreshes.

Adding a new individual row does not silently enable that currency globally on
ordinary Save. The panel shows any missing currencies; use **Use this provider
and enable currencies** to add them. Removing a row never removes a currency
from InvenTree's Supported Currencies list.

If you use environment/configuration overrides for `CURRENCY_CODES` or
`CURRENCY_UPDATE_PLUGIN`, update those at the server level; the panel reports
when such an override prevents applying your choice.

## Alternative: install from GitHub

This works **only after the completed local files have been pushed to GitHub**.
Use a tested commit SHA in place of `COMMIT_SHA` and the correct subdirectory.
Add either or both lines to `plugins.txt`:

```text
inventree-lyd-individual-exchange @ git+https://github.com/OmarShebani/inventree-manual-lyd-currency-exchange-rate-plugin.git@COMMIT_SHA#subdirectory=plugins/individual
inventree-lyd-global-exchange @ git+https://github.com/OmarShebani/inventree-manual-lyd-currency-exchange-rate-plugin.git@COMMIT_SHA#subdirectory=plugins/global
```

Then follow the same installation, restart, and activation steps. A private
repository requires Git credentials available to the container; do not put
access tokens in committed files.

If you downloaded a source ZIP, extract it first. Each `plugins/individual/` or
`plugins/global/` directory is pip-installable. For Docker, wheel installation
above is easier to persist reliably.

## Troubleshooting and switching

- **Plugin missing:** confirm it is installed in the InvenTree Python environment
  and restart both services. Installing on your host computer alone is not enough.
- **Custom panel does not load:** confirm URL integration is enabled and collect
  static files with `docker compose exec inventree-server invoke static`, then
  reload your browser. Check server logs for the specific import or URL error.
- **Automatic currency unavailable:** the original provider only supports its
  currency list. Use a supported intermediary, or (individual plugin only) enter
  a manual rate for the unsupported target. A manual unsupported global currency
  cannot provide online cross-rates to other currencies.
- **Switch variants:** open the other plugin, verify its separate saved settings,
  then use **Use this provider and enable currencies**. Confirm a successful
  refresh. Merely activating another plugin does not switch providers.
- **Return to the original provider:** first remove LYD and any other unsupported
  currencies from Supported Currencies (change Default Currency first if it is
  LYD), select InvenTreeCurrencyExchange, and refresh. The original provider cannot
  update a table containing LYD. Do not deactivate the selected plugin first.

The package has automated tests against rate calculations, authenticated API
views, and InvenTree 1.5.2's actual exchange backend. Installation has not been
validated inside your Docker/PostgreSQL deployment.

Reference: [InvenTree plugin installation](https://docs.inventree.org/en/1.5.x/plugins/install/).
