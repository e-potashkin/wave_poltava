// i18n-card — one card, two languages, chosen by the profile language.
//
//   type: custom:i18n-card
//   strings:
//     lamp_name: { en: Bedside lamp, uk: Приліжкова лампа }
//   card:
//     type: custom:mushroom-light-card
//     entity: light.philips_light_moonlight
//     name: "@@lamp_name@@"
//
// WHY
//   Home Assistant localises its own UI per user, but a card label is a plain
//   config string. Only JavaScript sees `hass.language`. This wrapper fills the
//   `@@key@@` placeholders with the string for the signed-in user, then builds
//   the real card with `createCardElement`, so every card type, including
//   mushroom, heading, entities and power-flow, keeps its own look and controls.
//
// WHEN IT REBUILDS
//   On the first `hass` and whenever the language changes. Every other `hass`
//   update is forwarded to the inner card, so the wrapper costs nothing after
//   the first build.
//
// LIMITS
//   A card that patches the DOM at the view level (bubble-card pop-ups) should
//   not be wrapped; its label stays a config string. A browser_mod pop-up title
//   is not a card either, so it cannot be localised this way.

const TAG = 'i18n-card';

// The section asks for grid options the moment it creates the wrapper, before
// `loadCardHelpers()` has resolved and the inner card exists. With no answer it
// gives the card a full row, then reflows to the two-column row when the inner
// card reports columns=6. Eugene saw that as "the Smart socket and Remote take
// a row, then become next to each other" (2026-10-21 21:17), and then the same
// on the two security cards (21:24). These hints are the values the cards
// report after they render.
const GRID_HINTS = {
  'custom:mushroom-entity-card': { columns: 6, rows: 1, min_columns: 4, min_rows: 1 },
  'custom:mushroom-template-card': { columns: 6, rows: 1 },
};

const langOf = (hass) => (String((hass && hass.language) || 'en').toLowerCase().startsWith('uk') ? 'uk' : 'en');

class I18nCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    // display: contents keeps the wrapper out of the layout: the inner card is
    // the grid item of a section slot and the flex item of a bubble pop-up, the
    // same place it had before it was wrapped. A block wrapper here moved the
    // Apple TV remote to the left of its pop-up (measured 2026-10-21).
    const style = document.createElement('style');
    style.textContent = ':host{display:contents}';
    this.shadowRoot.appendChild(style);
    this._lang = null;
    this._inner = null;
    this._build = 0;
  }

  setConfig(config) {
    if (!config || !config.card) throw new Error('i18n-card needs a `card`');
    this._config = config;
    this._strings = config.strings || {};
    this._lang = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._inner || langOf(hass) !== this._lang) {
      this._render();
      return;
    }
    this._inner.hass = hass;
  }

  _fill(text, lang) {
    return text.replace(/@@([a-z0-9_]+)@@/gi, (whole, key) => {
      const entry = this._strings[key];
      if (!entry) return whole;
      return entry[lang] ?? entry.en ?? whole;
    });
  }

  _localize(node, lang) {
    if (typeof node === 'string') return this._fill(node, lang);
    if (Array.isArray(node)) return node.map((item) => this._localize(item, lang));
    if (node && typeof node === 'object') {
      const out = {};
      for (const [key, value] of Object.entries(node)) out[key] = this._localize(value, lang);
      return out;
    }
    return node;
  }

  async _render() {
    if (!this._config) return;
    const lang = langOf(this._hass);
    const build = ++this._build;
    let helpers;
    try {
      helpers = await window.loadCardHelpers();
    } catch {
      return;
    }
    if (build !== this._build) return;
    const element = helpers.createCardElement(this._localize(this._config.card, lang));
    if (this._hass) element.hass = this._hass;
    if (this._inner) this._inner.remove();
    this._inner = element;
    this._lang = lang;
    this.shadowRoot.appendChild(element);
  }

  getCardSize() {
    return this._inner?.getCardSize?.() ?? 1;
  }

  getGridOptions() {
    return this._inner?.getGridOptions?.()
      ?? this._config?.grid_options
      ?? GRID_HINTS[this._config?.card?.type];
  }
}

if (!customElements.get(TAG)) customElements.define(TAG, I18nCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: TAG,
  name: 'i18n card',
  description: 'Wraps one card and fills @@key@@ labels for the profile language (en/uk).',
  preview: false,
});
