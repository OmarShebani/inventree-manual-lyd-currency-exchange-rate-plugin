# LYD Exchange Rates — Global Only

Independent InvenTree 1.5.2 plugin. Defaults to **1 USD = 10 LYD**.

Install this package in the InvenTree Python environment, restart server and worker,
activate it in Settings → Admin Center → Plugins, and open Plugin Configuration.
Enable URL integration. Use the page's **Use this provider and enable currencies**
button to select it and add LYD through native InvenTree settings.

Only one currency provider can be selected at a time. The original provider must
remain active for online rates. Settings and snapshots are stored in this plugin's
own database metadata. No database migrations or core patches are required.

See the repository's [installation guide](https://github.com/blank404-sh/inventree-manual-lyd-currency-exchange-rate-plugin/blob/main/docs/INSTALL.md).
