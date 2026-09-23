/* Native InvenTree custom settings entrypoint. No external scripts or build runtime. */
export function renderPluginSettings(target, context) {
  const root = document.createElement('section');
  root.className = 'lyd-settings';
  target.replaceChildren(root);
  let data, draft, dirty = false, busy = false, notice = '', failed = false;
  const endpoint = context.context.endpoint;
  const css = `
    .lyd-settings {font:inherit; line-height:1.5; color:inherit; max-width:1100px}
    .lyd-settings h2 {font-size:1.35rem; margin:0 0 8px}
    .lyd-settings p {margin:8px 0 16px}
    .lyd-settings .lyd-box {border:1px solid var(--mantine-color-default-border,#9ca3af);border-radius:8px;padding:16px;margin:16px 0}
    .lyd-settings .lyd-grid {display:flex;gap:12px;flex-wrap:wrap;align-items:end}
    .lyd-settings label {display:flex;flex-direction:column;gap:6px;flex:1;min-width:140px}
    .lyd-settings input,.lyd-settings select,.lyd-settings button {font:inherit;padding:8px;border-radius:5px;border:1px solid var(--mantine-color-default-border,#9ca3af);color:inherit;background:var(--mantine-color-body,#fff);max-width:100%;min-height:40px}
    .lyd-settings button {cursor:pointer;flex:none}
    .lyd-settings button:disabled {cursor:default;opacity:.55}
    .lyd-settings .lyd-primary {background:#1764b0;color:white;border-color:#1764b0}
    .lyd-settings .lyd-note {border-left:4px solid #b98116;padding:10px 14px;background:var(--mantine-color-default-hover,#f3f4f6)}
    .lyd-settings .lyd-error {border-left-color:#db4646}
    .lyd-settings .lyd-muted {font-size:.9em;opacity:.8}
    .lyd-settings table {width:100%;border-collapse:collapse}
    .lyd-settings td,.lyd-settings th {text-align:left;padding:8px;border-bottom:1px solid var(--mantine-color-default-border,#ddd)}
    .lyd-settings .lyd-scroll {overflow-x:auto}
    .lyd-settings button:focus-visible,.lyd-settings input:focus-visible,.lyd-settings select:focus-visible {outline:3px solid #5e9ce6;outline-offset:2px}
  `;
  function el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }
  function mark() {
    dirty = true;
    const refresh = root.querySelector('[data-refresh]');
    if (refresh) refresh.disabled = true;
    const status = root.querySelector('[role="status"]');
    if (status) status.textContent = 'Unsaved changes.';
  }
  function label(text, control) {
    const node = el('label', text); control.setAttribute('aria-label', text); node.append(control); return node;
  }
  function select(options, value, change, disabled = false) {
    const node = el('select');
    for (const [key, title] of options) {
      const option = el('option', title); option.value = key; node.append(option);
    }
    node.value = value; node.disabled = busy || disabled;
    node.onchange = () => {change(node.value); mark(); draw();};
    return node;
  }
  function button(text, action, disabled = false, primary = false) {
    const node = el('button', text, primary ? 'lyd-primary' : '');
    node.type = 'button'; node.disabled = busy || disabled; node.onclick = action; return node;
  }
  function currencyOptions(excluded = []) {
    return data.currencies.filter(c => !excluded.includes(c.code)).map(c => [c.code, `${c.code} — ${c.name}`]);
  }
  function reciprocal(value) {
    // Decimal division using integers, avoiding floating-point drift in direction switches.
    if (!/^\d+(\.\d+)?$/.test(value)) return '';
    const [whole, fraction = ''] = value.split('.');
    const denominator = BigInt(whole + fraction);
    if (!denominator) return '';
    const digits = ((10n ** BigInt(fraction.length + 24)) / denominator).toString().padStart(25, '0');
    return (digits.slice(0, -24) + '.' + digits.slice(-24)).replace(/0+$/, '').replace(/\.$/, '');
  }
  function message(error) {
    const detail = error.response?.data;
    return typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : error.message;
  }
  async function request(method, body) {
    const response = await context.api[method](endpoint, ...(body === undefined ? [] : [body]), {timeout:120000});
    return response.data;
  }
  function accept(result) { data = result; draft = structuredClone(data.config); dirty = false; }
  async function load() {
    busy = true; draw();
    try { accept(await request('get')); notice = ''; failed = false; }
    catch (error) { notice = message(error); failed = true; }
    finally { busy = false; draw(); }
  }
  async function act(action) {
    busy = true; notice = ''; failed = false; draw();
    try {
      if (dirty) accept(await request('put', {revision:data.revision, config:draft}));
      if (action === 'enable' || (action === 'save' && data.selected) || action === 'refresh') {
        accept(await request('post', {action:action === 'enable' ? 'enable' : 'refresh'}));
      }
      notice = data.error ? 'Update failed. The previous complete rates remain in use.' :
        data.selected ? 'Settings saved and rates refreshed.' : 'Settings saved. Select this provider to apply its rates.';
      failed = Boolean(data.error);
      context.queryClient?.invalidateQueries();
    } catch (error) { notice = message(error); failed = true; }
    finally { busy = false; draw(); }
  }
  function draw() {
    root.replaceChildren(el('style', css));
    root.append(el('h2', data?.title || 'LYD Exchange Rates'));
    if (notice) {
      const status = el('p', notice, 'lyd-note' + (failed ? ' lyd-error' : ''));
      status.setAttribute('role', failed ? 'alert' : 'status'); root.append(status);
    }
    if (!data) { root.append(el('p', busy ? 'Loading settings…' : 'Could not load settings.'));
      if (!busy) root.append(button('Retry', load)); return; }
    root.append(el('p', data.individual ?
      'Set individual LYD rates, or calculate through another currency. Currencies without a row use the global intermediary.' :
      'Enter one manual LYD rate. All other currencies follow InvenTree’s original online provider.'));
    if (data.individual) root.append(el('p',
      'Individual overrides also change non-LYD conversions. For example, 1 USD = 10 LYD and 1 EUR = 20 LYD imply 1 EUR = 2 USD throughout InvenTree.', 'lyd-note'));
    root.append(el('p', data.selected ? 'This is the selected currency provider.' : 'This provider is not selected. Its settings do not currently control InvenTree.', 'lyd-muted'));
    const global = el('div', undefined, 'lyd-box');
    global.append(label('Global intermediary (required, manual rate only)', select(currencyOptions(), draft.global_currency, code => {
      draft.global_currency = code;
      const old = draft.rows[code];
      const row = old?.mode === 'manual' ? old : {mode:'manual', direction:'foreign_to_lyd', value:''};
      draft.rows = data.individual ? {...draft.rows, [code]:row} : {[code]:row};
    })));
    global.append(el('p', 'USD starts at 1 USD = 10 LYD. Enter a rate when choosing a different global currency.', 'lyd-muted'));
    root.append(global);
    const order = [draft.global_currency, ...Object.keys(draft.rows).filter(c => c !== draft.global_currency).sort()];
    for (const code of order) {
      const row = draft.rows[code], isGlobal = code === draft.global_currency;
      const box = el('div', undefined, 'lyd-box');
      box.append(el('strong', code + (isGlobal ? ' · Global intermediary' : '')));
      const grid = el('div', undefined, 'lyd-grid');
      grid.append(label('Mode', select([['manual','Manual'],['auto','Calculate through a currency']], row.mode, mode => {
        draft.rows[code] = mode === 'manual' ? {mode, direction:'foreign_to_lyd', value:''} : {mode, via:draft.global_currency};
      }, isGlobal)));
      if (row.mode === 'manual') {
        grid.append(label('Rate direction', select([
          ['foreign_to_lyd', `1 ${code} = … LYD`], ['lyd_to_foreign', `1 LYD = … ${code}`]
        ], row.direction, direction => {row.value = reciprocal(row.value); row.direction = direction;})));
        const input = el('input'); input.type = 'text'; input.inputMode = 'decimal';
        input.value = row.value; input.placeholder = 'Enter a positive rate'; input.required = true;
        input.disabled = busy; input.maxLength = 50;
        input.oninput = () => {row.value = input.value; mark();};
        grid.append(label(row.direction === 'foreign_to_lyd' ? `LYD for 1 ${code}` : `${code} for 1 LYD`, input));
      } else {
        grid.append(label(`Calculate LYD → intermediary → ${code}`, select(currencyOptions([code]), row.via, via => {row.via = via;})));
      }
      if (data.individual) grid.append(button('Remove ' + code, () => {delete draft.rows[code]; mark(); draw();}, isGlobal));
      box.append(grid); root.append(box);
    }
    if (data.individual) {
      const options = currencyOptions(Object.keys(draft.rows));
      if (options.length) {
        const add = el('div', undefined, 'lyd-grid');
        const choice = select(options, options[0][0], () => {});
        // Selection here is not a configuration change until Add is pressed.
        choice.onchange = null;
        add.append(label('Add an individual currency', choice), button('Add currency', () => {
          draft.rows[choice.value] = {mode:'auto', via:draft.global_currency}; mark(); draw();
        })); root.append(add);
      }
      root.append(el('p', 'Removing a row restores the global calculation for that currency. It does not remove the currency from InvenTree.', 'lyd-muted'));
    }
    const actions = el('div', undefined, 'lyd-grid');
    actions.append(button(busy ? 'Working…' : 'Save settings and refresh', () => act('save'), false, true));
    actions.append(button('Use this provider and enable currencies', () => act('enable')));
    const refresh = button('Refresh saved rates', () => act('refresh'), dirty || !data.selected);
    refresh.dataset.refresh = 'true'; actions.append(refresh);
    actions.append(button('Reload saved settings', load));
    root.append(actions);
    const missing = ['LYD', ...Object.keys(draft.rows)].filter(c => !data.enabled_currencies.includes(c));
    if (missing.length) root.append(el('p', 'Not yet enabled in InvenTree: ' + missing.join(', ') + '. Use “Use this provider and enable currencies” to add them.', 'lyd-note'));
    const snapshot = data.snapshot;
    root.append(el('p', snapshot ? 'Last complete calculation: ' + new Date(snapshot.at).toLocaleString() : 'No successful calculation yet.', 'lyd-muted'));
    if (snapshot && snapshot.revision !== data.revision) root.append(el('p', 'Saved settings have not yet produced a complete new rate table.', 'lyd-note'));
    if (data.error) root.append(el('p', data.error, 'lyd-note lyd-error'));
    if (snapshot) {
      const scroll = el('div', undefined, 'lyd-scroll'), table = el('table');
      const head = el('tr'); ['Currency','1 currency in LYD','1 LYD in currency'].forEach(t => head.append(el('th', t)));
      table.append(head);
      for (const [code, value] of Object.entries(snapshot.lyd).sort()) {
        if (code === 'LYD') continue;
        const tr = el('tr'); [code, (1 / Number(value)).toLocaleString(undefined,{maximumSignificantDigits:10}),
          Number(value).toLocaleString(undefined,{maximumSignificantDigits:10})].forEach(t => tr.append(el('td', t)));
        table.append(tr);
      }
      scroll.append(table); root.append(scroll);
      root.append(el('p', 'Preview of the last complete calculation. InvenTree stores rates to six decimal places.', 'lyd-muted'));
    }
  }
  load();
}
