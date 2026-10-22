// i18n-chrome — the view tabs and the sidebar entry in the profile language.
//
//   /local/i18n-chrome.js, type module
//
// WHY
//   Home Assistant localises its own panels (Енергія, Активність) but a storage
//   dashboard title and a view title are config strings. With the profile in
//   Ukrainian the cards were translated by custom:i18n-card and the chrome above
//   them still read "Home" and "Power & Safety" (Eugene, 2026-10-21).
//
// WHAT IT DOES
//   Watches the page and writes the title into:
//     - <ha-tab-group-tab data-path="...">           the view tabs
//     - #sidebar-panel-dashboard-home .item-text     the sidebar entry
//     - hui-root .main-title                        the page header
//       (edit mode shows the dashboard title there, not a tab)
//   The element is only touched when its text differs, so the observer does not
//   feed itself. A 1.5 s timer covers a language switch: HA redraws the sidebar
//   without a DOM event this script can subscribe to first.
//
// LIMITS
//   Only the paths in TITLES are translated. The browser tab title stays as HA
//   builds it.

const TITLES = {
  'dashboard-home': { en: 'Home', uk: 'Головна' },
  home: { en: 'Home', uk: 'Головна' },
  'power-safety': { en: 'Power & Safety', uk: 'Живлення та безпека' },
};

// The dashboard chrome is Ukrainian even when the Home Assistant profile is
// English: the cards, the view names and the reason rows are Ukrainian, so a
// lone English "Home" above them reads as a fault. Set FORCE_UK to false to
// follow the profile language again.
const FORCE_UK = true;

const langOf = () => {
  if (FORCE_UK) return 'uk';
  const root = document.querySelector('home-assistant');
  const raw = (root && root.hass && root.hass.language) || document.documentElement.lang || 'en';
  return String(raw).toLowerCase().startsWith('uk') ? 'uk' : 'en';
};

const deep = (sel) => {
  const found = [];
  const walk = (root) => {
    if (!root) return;
    if (root.querySelectorAll) root.querySelectorAll(sel).forEach((el) => found.push(el));
    if (root.querySelectorAll) root.querySelectorAll('*').forEach((el) => { if (el.shadowRoot) walk(el.shadowRoot); });
  };
  walk(document);
  return found;
};

const labelOf = (path, lang) => {
  const entry = TITLES[path];
  return entry ? entry[lang] ?? entry.en : null;
};

// Replaces the first non-empty text node of the element, keeping its children
// (the icon) in place.
const setText = (el, text) => {
  if (!el) return false;
  const nodes = [...el.childNodes].filter((n) => n.nodeType === 3 && n.nodeValue.trim());
  const node = nodes[0];
  if (node) {
    if (node.nodeValue.trim() === text) return false;
    node.nodeValue = text;
    return true;
  }
  return false;
};

const apply = () => {
  const lang = langOf();
  let changed = false;
  for (const el of deep('ha-tab-group-tab')) {
    const path = el.getAttribute('data-path');
    const text = labelOf(path, lang);
    if (!text) continue;
    if (setText(el, text)) changed = true;
    if (el.getAttribute('aria-label') !== text) el.setAttribute('aria-label', text);
  }
  const side = deep('#sidebar-panel-dashboard-home .item-text')[0];
  const sideText = labelOf('dashboard-home', lang);
  if (side && sideText && side.textContent.trim() !== sideText) {
    side.textContent = sideText;
    changed = true;
  }

  // The page header. Edit mode shows the dashboard title here; a view without
  // tabs shows the view title. The path tells which one it is.
  const parts = location.pathname.split('/').filter(Boolean);
  const dashboardKey = parts[0];
  const viewKey = parts[1];
  const editing = location.search.includes('edit');
  const headerKey = editing ? dashboardKey : (viewKey && TITLES[viewKey] ? viewKey : dashboardKey);
  const headerText = labelOf(headerKey, lang);
  if (headerText) {
    for (const root of deep('hui-root')) {
      const title = root.shadowRoot?.querySelector('.main-title');
      if (title && setText(title, headerText)) changed = true;
    }
  }
  return changed;
};

let queued = false;
const schedule = () => {
  if (queued) return;
  queued = true;
  setTimeout(() => { queued = false; apply(); }, 150);
};

new MutationObserver(schedule).observe(document, { childList: true, subtree: true, characterData: true });
setInterval(apply, 1500);
apply();
