/* AMP • Dota Hub — vanilla JS Telegram Mini App, no build chain. */
'use strict';

const tg = window.Telegram?.WebApp;
const root = document.querySelector('#app');
const modalRoot = document.querySelector('#modal-root');
const conn = document.querySelector('#connection');
const toastBox = document.querySelector('#toast');
const state = {
  me: null, dota: null, amp: null, tab: 'dota', server: null, serverTab: 'overview',
  settings: {}, search: '', player: 'all', outcome: 'all', loading: false,
  busy: false, lastUpdate: null,
};
let toastTimer;

function el(tag, className = '', text = null) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== null && text !== undefined) n.textContent = String(text);
  return n;
}
function add(parent, ...children) {
  for (const child of children.flat()) if (child !== null && child !== undefined) parent.append(child);
  return parent;
}
function btn(label, callback, className = 'btn') {
  const n = el('button', className, label);
  n.type = 'button';
  n.addEventListener('click', callback);
  return n;
}
function field(label, input) {
  const holder = el('div', 'field');
  const l = el('label', '', label);
  input.id = `f-${Math.random().toString(36).slice(2)}`;
  l.htmlFor = input.id;
  return add(holder, l, input);
}
function notice(text, error = false) {
  clearTimeout(toastTimer);
  toastBox.textContent = text;
  toastBox.style.borderColor = error ? '#9a484a' : '';
  toastBox.classList.add('visible');
  toastTimer = setTimeout(() => toastBox.classList.remove('visible'), 3200);
  if (error) tg?.HapticFeedback?.notificationOccurred('error');
}
function dateLabel(seconds) {
  if (!seconds) return 'Brak daty';
  return new Intl.DateTimeFormat('pl-PL', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(seconds * 1000));
}
function duration(seconds) {
  if (!Number.isFinite(Number(seconds))) return '—';
  const x = Math.max(0, Math.round(seconds));
  return `${Math.floor(x / 60)}:${String(x % 60).padStart(2, '0')}`;
}
function percent(x) { return typeof x === 'number' && Number.isFinite(x) ? `${Math.round(x)}%` : '—'; }
function safeNum(x, fallback = '—') { return x == null ? fallback : Number(x).toLocaleString('pl-PL'); }
function rankName(tier) {
  if (!tier) return 'Ranga nieznana';
  const names = {1:'Herald',2:'Guardian',3:'Crusader',4:'Archon',5:'Legend',6:'Ancient',7:'Divine',8:'Immortal'};
  const n = Number(tier);
  return (names[Math.floor(n/10)] || 'Ranga') + (n < 80 ? ` ${n%10 || ''}` : '');
}
function modeName(m) {
  const names = { 1: 'All Pick', 2: 'Captains Mode', 3: 'Random Draft', 4: 'Single Draft', 22: 'All Pick', 23: 'Turbo' };
  return `${names[m.game_mode] || 'Tryb ' + (m.game_mode ?? '?')}${m.lobby_type === 7 ? ' • Ranked' : ''}`;
}
function requestId() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  const arr = new Uint8Array(16);
  crypto.getRandomValues(arr);
  return Array.from(arr, b => b.toString(16).padStart(2, '0')).join('');
}
async function api(path, data) {
  const opts = { method: data === undefined ? 'GET' : 'POST', cache: 'no-store',
    headers: { 'X-Telegram-Init-Data': tg?.initData || '' }, signal: AbortSignal.timeout(55000) };
  if (data !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(data);
  }
  let response;
  try { response = await fetch(path, opts); }
  catch (e) { throw new Error(e.name === 'TimeoutError' ? 'Serwer zbyt długo nie odpowiada' : 'Brak połączenia z panelem'); }
  const json = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(json.error || `Błąd HTTP ${response.status}`);
  return json;
}
function setConnection(ok, label) {
  conn.classList.toggle('online', ok);
  conn.classList.toggle('error', !ok);
  conn.querySelector('span:last-child').textContent = label;
}
function closeModal() {
  modalRoot.replaceChildren();
  tg?.BackButton?.hide();
  syncBackButton();
}
function modal(title, subtitle = '') {
  closeModal();
  const scrim = el('div', 'modal-scrim');
  const box = el('div', 'modal');
  const close = btn('✕', closeModal, 'modal-close');
  add(box, close, el('h2', '', title));
  if (subtitle) add(box, el('p', 'modal-sub', subtitle));
  add(scrim, box);
  scrim.addEventListener('click', event => { if (event.target === scrim) closeModal(); });
  modalRoot.append(scrim);
  tg?.BackButton?.show();
  return box;
}
function syncBackButton() {
  if (!tg?.BackButton) return;
  if (modalRoot.children.length || state.server) tg.BackButton.show();
  else tg.BackButton.hide();
}
function goBack() {
  if (modalRoot.children.length) return closeModal();
  if (state.server) { state.server = null; state.serverTab = 'overview'; render(); }
}
function section(parent, title, actionText = null, action = null) {
  const line = el('div', 'section-header');
  line.append(el('h2', 'section-title', title));
  if (actionText) line.append(btn(actionText, action, 'section-action'));
  parent.append(line);
}
function stat(value, label, tone = '') {
  const box = el('div', 'stat');
  add(box, el('div', 'num ' + tone, value), el('div', 'desc', label));
  return box;
}
function empty(title, detail, symbol = '◈') {
  const box = el('div', 'empty');
  return add(box, el('div', 'symbol', symbol), el('strong', '', title), el('div', '', detail));
}
function heroPortrait(m) {
  const box = el('div', 'hero-portrait', '✦');
  if (m.hero_slug && /^[a-z0-9_]+$/.test(m.hero_slug)) {
    const img = el('img');
    img.alt = m.hero_name || '';
    img.loading = 'lazy';
    img.referrerPolicy = 'no-referrer';
    img.src = `https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/${m.hero_slug}.png`;
    img.addEventListener('error', () => img.remove());
    box.append(img);
  }
  return box;
}
function setTab(name) {
  state.tab = name;
  state.server = null;
  state.search = '';
  document.querySelectorAll('.nav-btn').forEach(n => n.classList.toggle('active', n.dataset.tab === name));
  render();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function render() {
  if (!state.me) return;
  root.replaceChildren();
  if (state.server) renderServer();
  else if (state.tab === 'dota' && state.me.admin) renderDota();
  else renderAmp();
  syncBackButton();
}

/* --- Dota 2 --- */
function renderDota() {
  const data = state.dota || { players: [], matches: [], totals: {}, notifications: true };
  const hero = el('div', 'hero');
  add(hero, el('div', 'section-kicker', 'MATCH INTELLIGENCE'), el('h1', '', 'Dota 2 · Obserwowani'),
    el('p', '', 'Ostatnie mecze, historia bohaterów i wyniki. Bez przewijania powiadomień Telegrama.'));
  root.append(hero);
  const summaries = data.matches || [];
  const wins = summaries.filter(x => x.win).length;
  const stats = el('div', 'stats-row');
  add(stats, stat(data.players.length, 'Obserwowani'),
    stat(summaries.length, 'Mecze w historii'),
    stat(summaries.length ? `${Math.round(100 * wins / summaries.length)}%` : '—', 'Win rate', 'green'));
  root.append(stats);
  section(root, 'Obserwowani gracze', '+ Dodaj', showWatchModal);
  const profiles = el('div', 'profile-list');
  if (!data.players.length) profiles.append(empty('Nikogo jeszcze nie obserwujesz', 'Dodaj Friend ID z Dota 2 lub adres profilu OpenDota.', '🎯'));
  for (const p of data.players) profiles.append(playerCard(p, data.totals?.[p.account_id]));
  root.append(profiles);
  section(root, 'Historia meczów', '↻ Odśwież', () => refresh(true));
  const filters = el('div', 'filters');
  const players = [{ value: 'all', name: 'Wszyscy' }, ...data.players.map(p => ({ value: String(p.account_id), name: p.name }))];
  for (const p of players) filters.append(btn(p.name, () => { state.player = p.value; render(); },
    'chip' + (state.player === p.value ? ' active' : '')));
  root.append(filters);
  const results = el('div', 'filters');
  for (const [value, label] of [['all', 'Wszystkie'], ['win', 'Wygrane'], ['loss', 'Przegrane']]) {
    results.append(btn(label, () => { state.outcome = value; render(); },
      'chip' + (state.outcome === value ? ' active' : '')));
  }
  root.append(results);
  const visible = summaries.filter(m => (state.player === 'all' || String(m.account_id) === state.player)
    && (state.outcome === 'all' || (state.outcome === 'win') === m.win));
  const matches = el('div', 'match-list');
  if (!visible.length) matches.append(empty('Brak meczów dla tych filtrów', 'Historia zapełnia się podczas synchronizacji OpenDota.', '▤'));
  for (const m of visible.slice(0, 250)) matches.append(matchCard(m));
  root.append(matches);
  const toggle = el('div', 'panel spaced');
  const label = el('div');
  add(label, el('strong', '', 'Powiadomienia o nowych meczach'),
    el('div', 'sub', 'Historia zapisuje się niezależnie od powiadomień.'));
  const turn = btn(data.notifications ? '🔔 Włączone' : '🔕 Wyłączone', async () => {
    try { await api('/api/dota/notifications', { enabled: !data.notifications });
      data.notifications = !data.notifications; notice('Zmieniono powiadomienia'); render(); }
    catch (e) { notice(e.message, true); }
  }, 'btn small');
  toggle.style.display = 'flex'; toggle.style.alignItems = 'center'; toggle.style.justifyContent = 'space-between'; toggle.style.gap = '12px';
  add(toggle, label, turn);
  root.append(toggle);
}
function playerCard(p, total = {}) {
  const box = el('div', 'profile');
  const avatar = el('div', 'avatar', (p.name || '?').slice(0, 1).toUpperCase());
  const center = el('div', 'content');
  const wr = total.total ? `${Math.round(total.wins / total.total * 100)}% wygranych` : 'Brak meczów';
  add(center, el('strong', '', p.name), el('div', 'sub', `${rankName(p.rank_tier)} • ${wr}${p.public === 0 ? ' • Brak publicznych meczów' : ''}`));
  const actions = el('div', 'profile-actions');
  add(actions, btn('Mecze', () => { state.player = String(p.account_id); state.outcome = 'all'; render();
    document.querySelector('.match-list')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 'btn small'),
  btn('✕', () => removePlayer(p), 'ghost'));
  return add(box, avatar, center, actions);
}
function matchCard(m) {
  const box = el('button', 'match'); box.type = 'button';
  const content = el('div', 'match-content');
  add(content, add(el('div', 'match-top'), el('strong', '', m.hero_name)),
    add(el('div', 'match-bottom'), el('span', '', m.player_name), el('span', '', '·'),
      el('span', '', dateLabel(m.start_time)), el('span', '', '·'), el('span', '', duration(m.duration))));
  const right = el('div', 'match-right');
  add(right, el('span', `badge ${m.win ? 'win' : 'loss'}`, m.win ? 'ZWYCIĘSTWO' : 'PORAŻKA'),
    el('span', 'muted', `${m.kills ?? 0}/${m.deaths ?? 0}/${m.assists ?? 0} KDA`));
  add(box, heroPortrait(m), content, right);
  box.addEventListener('click', () => openMatch(m));
  return box;
}
function showWatchModal() {
  const box = modal('Obserwuj gracza', 'Friend ID (Steam32) albo link do profilu Steam, Dotabuff lub OpenDota.');
  const input = el('input'); input.placeholder = 'Np. 123456789'; input.autocomplete = 'off';
  box.append(field('Dota Friend ID / URL', input));
  box.append(btn('Dodaj do obserwowanych', async () => {
    const id = input.value.trim();
    if (!id) return notice('Wpisz ID gracza', true);
    try { await api('/api/dota/watch', { account_id: id, request_id: requestId() });
      closeModal(); notice('Dodano gracza'); await refresh(); }
    catch (e) { notice(e.message, true); }
  }, 'btn btn-primary full'));
}
function removePlayer(p) {
  const box = modal(`Usunąć ${p.name}?`, 'Wraz z obserwacją usunięta zostanie jego historia w lokalnej bazie.');
  add(box, btn('Usuń', async () => {
    try { await api('/api/dota/unwatch', { account_id: p.account_id, request_id: requestId() });
      if (state.player === String(p.account_id)) state.player = 'all';
      closeModal(); notice('Usunięto gracza'); await refresh(); }
    catch (e) { notice(e.message, true); }
  }, 'btn btn-danger full'), btn('Anuluj', closeModal, 'btn full'));
}
async function openMatch(m) {
  const box = modal(`${m.hero_name} • ${m.win ? 'Wygrana' : 'Przegrana'}`,
    `${m.player_name} • ${dateLabel(m.start_time)} • ${modeName(m)} • ${duration(m.duration)}`);
  box.append(add(el('div', 'stats-row'), stat(`${m.kills ?? 0}/${m.deaths ?? 0}/${m.assists ?? 0}`, 'K / D / A'),
    stat(safeNum(m.gpm), 'GPM'), stat(safeNum(m.xpm), 'XPM')));
  const loading = el('p', 'muted tiny', 'Pobieranie szczegółów meczu…'); box.append(loading);
  const link = el('a', 'btn full spaced', 'Otwórz mecz w OpenDota ↗');
  link.href = `https://www.opendota.com/matches/${m.match_id}`;
  link.target = '_blank'; link.rel = 'noopener noreferrer';
  box.append(link);
  try {
    const [result, itemData] = await Promise.all([
      api(`/api/dota/matches/${m.match_id}`),
      api('/api/dota/items').catch(() => ({ items: {} })),
    ]);
    const items = itemData.items || {};
    if (!box.isConnected) return;
    const table = el('div');
    const teams = [{ team: 'Radiant', members: result.players.filter(x => Number(x.player_slot) < 128), score: result.radiant_score },
      { team: 'Dire', members: result.players.filter(x => Number(x.player_slot) >= 128), score: result.dire_score }];
    for (const t of teams) {
      const h = el('div', 'team-bar');
      add(h, el('span', t.team === 'Radiant' ? 'green' : 'red', t.team), el('span', '', `${safeNum(t.score)} zabójstw`));
      table.append(h);
      if (!t.members.length) table.append(el('div', 'sub', 'Brak danych graczy w OpenDota'));
      for (const p of t.members) {
        const h = state.dota?.heroes?.[String(p.hero_id)] || {};
        const name = el('strong', '', p.personaname || h.name || `Hero #${p.hero_id || '?'}`);
        const info = el('div', 'sub', `${h.name || `Bohater #${p.hero_id || '?'}`} · GPM ${safeNum(p.gold_per_min)}`);
        const itemLine = el('div', 'item-strip');
        for (const id of [p.item_0, p.item_1, p.item_2, p.item_3, p.item_4, p.item_5]) {
          if (!Number(id)) continue;
          const item = items[String(id)] || {};
          const holder = el('span', 'item-icon', String(id)); holder.title = item.name || `Item #${id}`;
          if (item.img && /^\/apps\/dota2\/images\/[a-z0-9_/-]+\.png$/.test(item.img)) {
            const img = el('img'); img.loading = 'lazy'; img.alt = item.name || '';
            img.referrerPolicy = 'no-referrer';
            img.src = 'https://cdn.cloudflare.steamstatic.com' + item.img;
            img.addEventListener('error', () => img.remove()); holder.append(img);
          }
          itemLine.append(holder);
        }
        table.append(add(el('div', 'player-score'), add(el('div'), name, info, itemLine),
          el('span', 'score', `${p.kills ?? '—'}/${p.deaths ?? '—'}/${p.assists ?? '—'}`)));
      }
    }
    loading.replaceWith(table);
  } catch (e) { loading.textContent = e.message; }
}

/* --- AMP --- */
function renderAmp() {
  const header = el('div', 'hero amp-hero');
  add(header, el('div', 'section-kicker', 'CUBECODERS AMP'), el('h1', '', 'Centrum instancji'),
    el('p', '', 'Sterowanie serwerami, stan graczy i parametry maszyny z jednego miejsca.'));
  root.append(header);
  const instances = state.amp?.instances || [];
  const active = instances.filter(i => i.running && i.state === 20).length;
  const metrics = el('div', 'stats-row');
  add(metrics, stat(instances.length, 'Instancje'), stat(active, 'Gry online', 'green'),
    stat(instances.reduce((sum, i) => sum + (i.players || 0), 0), 'Gracze online'));
  root.append(metrics);
  section(root, 'Twoje serwery', '↻ Odśwież', () => refresh(true));
  const list = el('div', 'server-list');
  if (state.amp?.error) list.append(empty('AMP jest niedostępny', state.amp.error, '⚠'));
  else if (state.amp && !state.amp.configured) list.append(empty('AMP nie jest skonfigurowany',
    'Ustaw AMP_URL, AMP_USER i AMP_PASS w /etc/amp-tg-bot.env.', '▣'));
  else if (!instances.length) list.append(empty('Brak dostępnych instancji',
    'Nie znaleziono instancji przypisanych do tego konta.', '▣'));
  for (const inst of instances) list.append(serverCard(inst));
  root.append(list);
}
function metricLabel(m, isMemory = false) {
  if (!m || !Number.isFinite(Number(m.raw))) return 'Brak danych';
  if (!isMemory) return `${percent(m.pct)}`;
  const factor = (m.units || '').toUpperCase().startsWith('GB') ? 1 : 1024;
  return `${(m.raw / factor).toFixed(1)} GB${m.max ? ` / ${(m.max / factor).toFixed(1)} GB` : ''}`;
}
function meter(m, name, mem = false) {
  const outer = el('div');
  const label = el('div', 'meter-label');
  add(label, el('span', '', name), el('span', '', metricLabel(m, mem)));
  const progress = el('div', 'progress');
  const bar = el('i');
  bar.style.width = `${Math.min(100, Math.max(0, Number(m?.pct) || 0))}%`;
  progress.append(bar);
  return add(outer, label, progress);
}
function serverCard(inst) {
  const card = el('button', 'server-card'); card.type = 'button';
  const heading = el('div', 'server-header');
  const title = el('div', 'server-name');
  add(title, el('strong', '', inst.friendly || inst.name), el('div', 'sub', `${inst.module || 'Gra'} • ${inst.players || 0} online`));
  add(heading, el('div', 'server-icon', '▣'), title,
    el('span', `badge ${inst.busy ? 'busy' : inst.running && inst.state === 20 ? 'running' : 'stopped'}`,
      inst.busy ? 'W TOKU' : inst.running && inst.state === 20 ? 'ONLINE' : inst.running ? 'GOTOWA' : 'OFFLINE'));
  add(card, heading, add(el('div', 'meter-row'), meter(inst.cpu, 'CPU'), meter(inst.mem, 'RAM', true)));
  card.addEventListener('click', () => { state.server = inst.name; state.serverTab = 'overview';
    state.search = ''; render(); window.scrollTo({ top: 0, behavior: 'smooth' }); });
  return card;
}
function renderServer() {
  const inst = state.amp?.instances?.find(i => i.name === state.server);
  const header = el('div', 'breadcrumb');
  add(header, btn('‹', goBack, 'back'), el('h2', '', inst?.friendly || state.server));
  root.append(header);
  if (!inst) { root.append(empty('Instancja niedostępna', 'Odśwież listę serwerów.')); return; }
  const banner = el('div', 'panel');
  const label = el('div', 'section-kicker', 'STATUS INSTANCJI');
  const status = el('h2', '', inst.state_text || 'Nieznany'); status.style.margin = '9px 0';
  add(banner, label, status, el('div', 'sub', `${inst.module || 'Gra'} • ${inst.players || 0} graczy online`));
  if (inst.busy) add(banner, el('p', 'gold tiny', `Operacja w toku: ${inst.busy}`));
  root.append(banner);
  const tabs = el('div', 'tabstrip');
  const choices = [['overview', 'Sterowanie'], ['players', 'Gracze'], ['settings', 'Ustawienia']];
  if (state.me.admin) choices.push(['console', 'Konsola']);
  for (const [id, label] of choices) tabs.append(btn(label, () => {
    state.serverTab = id; render(); if (id === 'settings') ensureSettings(inst.name);
    if (id === 'players') loadPlayers(inst.name); if (id === 'console') loadConsole(inst.name);
  }, state.serverTab === id ? 'active' : ''));
  root.append(tabs);
  if (state.serverTab === 'overview') renderServerOverview(inst);
  if (state.serverTab === 'players') renderPlayers(inst);
  if (state.serverTab === 'settings') renderSettings(inst);
  if (state.serverTab === 'console' && state.me.admin) renderConsole(inst);
}
function renderServerOverview(inst) {
  root.append(add(el('div', 'stats-row'), stat(percent(inst.cpu?.pct), 'CPU'),
    stat(percent(inst.mem?.pct), 'RAM'), stat(inst.players ?? 0, 'Gracze')));
  section(root, 'Akcje serwera');
  const grid = el('div', 'actions-grid');
  const actions = [
    { id: 'start', icon: '▶', label: 'Start' }, { id: 'stop', icon: '■', label: 'Stop', danger: true },
    { id: 'restart', icon: '↻', label: 'Restart', danger: true }, { id: 'on', icon: '⏻', label: 'Instancja ON' },
    { id: 'off', icon: '◉', label: 'Instancja OFF', danger: true },
    { id: 'update', icon: '⇡', label: 'Aktualizuj', danger: true }, { id: 'backup', icon: '▤', label: 'Backup' }
  ];
  for (const a of actions) {
    const item = el('button', 'action-btn' + (a.danger ? ' danger' : '')); item.type = 'button';
    add(item, el('span', 'action-icon', a.icon), el('span', '', a.label));
    item.disabled = !!inst.busy || (!inst.running && !['start', 'on'].includes(a.id)) ||
      (inst.running && a.id === 'on');
    item.addEventListener('click', () => confirmAction(inst, a));
    grid.append(item);
  }
  root.append(grid);
  root.append(el('p', 'sub spaced', 'Start/Stop gry i włączenie/wyłączenie instancji AMP to osobne operacje. Potwierdzaj operacje mogące przerwać grę.'));
}
function confirmAction(inst, action) {
  const potentiallyDisruptive = ['stop', 'off', 'restart', 'update'].includes(action.id);
  const subtitle = potentiallyDisruptive ?
    `Czy wykonać „${action.label}” na ${inst.friendly}? Gracze online: ${inst.players || 0}.` :
    `Wykonać „${action.label}” dla ${inst.friendly}?`;
  const box = modal(action.label + ' · ' + inst.friendly, subtitle);
  const hasPlayers = potentiallyDisruptive && !!inst.players && state.me.warn_seconds > 0;
  if (hasPlayers) box.append(el('p', 'gold tiny',
    `Przy ostrzeżeniu bot spróbuje wysłać komunikat w grze i odczeka ${state.me.warn_seconds} s. Nie każda gra to obsługuje.`));
  const choices = [];
  if (hasPlayers) choices.push({ label: `⏳ Ostrzeż i odczekaj ${state.me.warn_seconds} s`, warn: true, css: 'btn btn-primary full' });
  choices.push({ label: potentiallyDisruptive ? '⚡ Wykonaj teraz' : 'Potwierdź', warn: false,
    css: potentiallyDisruptive ? 'btn btn-danger full' : 'btn btn-primary full' });
  for (const choice of choices) box.append(btn(choice.label, async () => {
    const id = requestId();
    try { await api(`/api/amp/instances/${encodeURIComponent(inst.name)}/action`,
      { action: action.id, confirmed: true, warn: choice.warn, request_id: id });
      closeModal(); notice('Zlecono operację. Postęp przyjdzie też w Telegramie.'); await refresh(); }
    catch (e) { notice(e.message, true); }
  }, choice.css));
  box.append(btn('Anuluj', closeModal, 'btn full'));
}
async function loadPlayers(name) {
  try { state.players = { name, loading: true }; render();
    const data = await api(`/api/amp/instances/${encodeURIComponent(name)}/players`);
    state.players = { name, list: data.players }; render(); }
  catch (e) { state.players = { name, error: e.message }; render(); }
}
function renderPlayers(inst) {
  section(root, 'Gracze online', '↻', () => loadPlayers(inst.name));
  const data = state.players?.name === inst.name ? state.players : null;
  if (!data || data.loading) return root.append(empty('Wczytywanie graczy', 'Pobieranie listy z AMP…', '◌'));
  if (data.error) return root.append(empty('Błąd', data.error));
  const list = el('div', 'profile-list');
  if (!data.list?.length) list.append(empty('Nikt nie gra', 'Serwer nie zgłasza aktywnych graczy.', '◉'));
  for (const name of data.list || []) {
    const item = el('div', 'profile');
    add(item, el('div', 'avatar', '◉'), el('strong', '', name));
    list.append(item);
  }
  root.append(list);
}
async function ensureSettings(name, force = false) {
  if (state.settings[name] && !force) return;
  state.settings[name] = { loading: true }; render();
  try { const data = await api(`/api/amp/instances/${encodeURIComponent(name)}/settings`);
    state.settings[name] = { groups: data.groups }; render(); }
  catch (e) { state.settings[name] = { error: e.message }; render(); }
}
function renderSettings(inst) {
  section(root, 'Konfiguracja', '↻', () => ensureSettings(inst.name, true));
  const search = el('input', 'search-input'); search.placeholder = 'Szukaj: MOTD, difficulty, world…';
  search.value = state.search;
  search.addEventListener('input', event => { state.search = event.target.value; showSettingGroups(inst); });
  root.append(search);
  const container = el('div', 'spaced'); container.id = 'setting-groups'; root.append(container);
  showSettingGroups(inst);
}
function showSettingGroups(inst) {
  const target = document.querySelector('#setting-groups');
  if (!target) return;
  target.replaceChildren();
  const data = state.settings[inst.name];
  if (!data || data.loading) return target.append(empty('Wczytywanie ustawień', 'Pobieranie konfiguracji z AMP…', '⚙'));
  if (data.error) return target.append(empty('Błąd konfiguracji', data.error));
  let found = 0;
  for (const group of data.groups || []) {
    const items = (group.items || []).filter(s =>
      `${s.name} ${s.node} ${s.desc}`.toLowerCase().includes(state.search.toLowerCase()));
    if (!items.length) continue;
    found += items.length;
    const details = el('details', 'setting-group'); details.open = Boolean(state.search.trim());
    details.append(el('summary', '', `${group.name} (${items.length})`));
    const body = el('div', 'setting-items');
    for (const s of items) {
      const item = el('div', 'setting-item');
      const main = add(el('div', 'setting-main'), el('strong', '', s.name),
        el('small', '', s.desc || s.node));
      const value = s.enum?.length ? s.enum.find(x => String(x[0]) === String(s.value))?.[1] || s.value : s.value;
      add(item, main, el('div', 'setting-val', String(value ?? '—')),
        btn('Edytuj', () => editSetting(inst.name, s), 'btn small'));
      body.append(item);
    }
    details.append(body); target.append(details);
  }
  if (!found) target.append(empty('Brak ustawień', 'Zmień wyszukiwaną frazę.'));
}
function editSetting(name, setting) {
  const box = modal(setting.name, setting.desc || setting.node);
  let input;
  if (setting.enum?.length) {
    input = el('select');
    for (const [key, label] of setting.enum) {
      const opt = el('option', '', label); opt.value = String(key); input.append(opt);
    }
    input.value = String(setting.value ?? '');
  } else if (setting.type === 'checkbox') {
    input = el('select');
    for (const [value, label] of [['true', 'Włączone'], ['false', 'Wyłączone']]) {
      const opt = el('option', '', label); opt.value = value; input.append(opt);
    }
    input.value = String(setting.value).toLowerCase() === 'true' ? 'true' : 'false';
  } else {
    input = el('input'); input.value = String(setting.value ?? '');
    input.maxLength = 1000;
  }
  box.append(field('Wartość', input));
  box.append(btn('Zapisz ustawienie', async () => {
    try {
      await api(`/api/amp/instances/${encodeURIComponent(name)}/settings`,
        { node: setting.node, value: input.value, request_id: requestId() });
      closeModal(); notice('Zapisano ustawienie'); await ensureSettings(name, true);
    } catch (e) { notice(e.message, true); }
  }, 'btn btn-primary full'));
  box.append(btn('Anuluj', closeModal, 'btn full'));
}
async function loadConsole(name) {
  state.console = { name, loading: true }; render();
  try { const data = await api(`/api/amp/instances/${encodeURIComponent(name)}/console`);
    state.console = { name, lines: data.lines }; render(); }
  catch (e) { state.console = { name, error: e.message }; render(); }
}
function renderConsole(inst) {
  section(root, 'Konsola', '↻', () => loadConsole(inst.name));
  const data = state.console?.name === inst.name ? state.console : null;
  const output = el('pre', 'console', data?.loading ? 'Ładowanie…' :
    data?.error || (data?.lines || []).join('\n') || 'Brak ostatnich wpisów.');
  root.append(output);
  const input = el('input'); input.placeholder = 'Komenda do konsoli gry'; input.autocomplete = 'off'; input.maxLength = 200;
  const f = field('Komenda (tylko administrator)', input);
  const submit = btn('Wyślij', async () => {
    if (!input.value.trim()) return;
    try { const data = await api(`/api/amp/instances/${encodeURIComponent(inst.name)}/console`,
      { command: input.value, request_id: requestId() });
      notice('Wysłano komendę'); input.value = '';
      state.console = { name: inst.name, lines: data.lines }; render(); }
    catch (e) { notice(e.message, true); }
  }, 'btn btn-primary full');
  add(root, f, submit, el('p', 'sub spaced', 'Komendy konsoli wykonują się z uprawnieniami AMP. Nie udostępniaj tej funkcji znajomym.'));
}

/* --- Bootstrap, polling and accessibility --- */
async function refresh(interactive = false) {
  if (state.busy) return;
  state.busy = true;
  if (interactive) document.querySelector('#reload').textContent = '◌';
  try {
    const me = await api('/api/me');
    state.me = me;
    if (!me.admin) {
      state.tab = 'amp';
      const tab = document.querySelector('[data-tab="dota"]');
      if (tab) tab.style.display = 'none';
    }
    const tasks = [api('/api/amp/instances')];
    if (me.admin) tasks.push(api('/api/dota'));
    const [ampResult, dotaResult] = await Promise.allSettled(tasks);
    state.amp = ampResult.status === 'fulfilled' ? ampResult.value :
      { configured: false, instances: [], error: ampResult.reason?.message || 'Brak połączenia z AMP' };
    if (me.admin) {
      if (dotaResult?.status === 'fulfilled') state.dota = dotaResult.value;
      else if (!state.dota) state.dota = { players: [], matches: [], totals: {}, notifications: true };
    }
    state.lastUpdate = new Date();
    setConnection(true, `Połączono • ${me.name} • ${new Intl.DateTimeFormat('pl-PL', { hour: '2-digit', minute: '2-digit' }).format(state.lastUpdate)}`);
    document.querySelectorAll('.nav-btn').forEach(n => n.classList.toggle('active', n.dataset.tab === state.tab));
    render();
    if (interactive) notice('Dane odświeżone');
  } catch (e) {
    if (!state.me) root.replaceChildren(empty('Nie można otworzyć panelu', e.message,
      '⚠'));
    setConnection(false, e.message);
    if (interactive) notice(e.message, true);
  } finally {
    state.busy = false;
    document.querySelector('#reload').textContent = '↻';
  }
}
function start() {
  tg?.ready(); tg?.expand();
  tg?.setBackgroundColor?.('#0d1117');
  tg?.setHeaderColor?.('#0d1117');
  tg?.BackButton?.onClick(goBack);
  document.querySelector('#reload').addEventListener('click', () => refresh(true));
  document.querySelectorAll('[data-tab]').forEach(n => n.addEventListener('click', () => {
    if (n.dataset.tab === 'dota' && state.me && !state.me.admin) return;
    setTab(n.dataset.tab);
  }));
  if (!tg?.initData) {
    root.replaceChildren(empty('Otwórz panel przez Telegrama',
      'Ta aplikacja wymaga poprawnie podpisanej sesji Telegram Mini Apps. Sam link w przeglądarce nie daje dostępu.', '◈'));
    setConnection(false, 'Brak sesji Telegrama');
    return;
  }
  refresh();
  setInterval(() => {
    // Keep focus, text edits and expanded settings groups stable while interacting.
    if (document.visibilityState !== 'visible' || modalRoot.children.length ||
        (state.server && ['settings', 'console'].includes(state.serverTab)) ||
        document.activeElement?.matches('input,textarea,select')) return;
    refresh();
  }, 20000);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && !modalRoot.children.length &&
        !(state.server && ['settings', 'console'].includes(state.serverTab)) &&
        Date.now() - (state.lastUpdate?.getTime() || 0) > 30000) refresh();
  });
}
start();
