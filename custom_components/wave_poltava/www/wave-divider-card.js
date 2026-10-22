// Wave divider — the activity logbook with one rail per wave.
//
// WHY
//   Eugene, 2026-10-18: "divide wave with line separator ... we can have curly
//   line to detach current wave from previous". The line landed, then became
//   straight and faint, and on 15:40 he chose a rail: "може вертикальна лінія
//   зліва?" — every wave is a block with a rail on the left.
//
// WHAT THIS IS
//   custom:multiple-logbook-card, subclassed. It keeps every option of the
//   original card and adds three things:
//
//     1  a 2 px rail on the left of every wave block
//     2  a caption at the top of the block: "ВІДБІЙ" and its time, small caps,
//        no icon, taken from the row of sensor.air_wave_local that reads "idle"
//     3  while our area is under alert there is no such row yet, so the card
//        draws its own caption: "ТРИВОГА" and the elapsed time, on a red rail.
//        The time is the alert that is running, not the wave: one wave can hold
//        an all-clear and a second alert (see _liveMinutes).
//     4  a message row shows the reason alone: "БпЛА" instead of
//        "Полтавський район — тривога по БпЛА Кременчуцький район — ...".
//        The whole sentence stays in the row tooltip.
//
//   The list is newest first, so a wave reads from its all-clear DOWN to its
//   first message: the all-clear row is the top row of the block, and that is why
//   it becomes the caption.
//
// DESIGN
//   The rail holds the block together and the caption names its edge. The two
//   horizontal rules of the card (the day separator) stay the only horizontal
//   lines, so the eye reads: day, then waves, then messages.
//
// CONFIG
//   type: custom:wave-divider-card
//   entities: [...]              as custom:multiple-logbook-card
//   divider:
//     entity: sensor.air_wave_local   the row that ends a wave
//     state: idle                     its state at the end
//     mode: rail                      rail (default) or line
//     thickness: 2                    rail width, px
//     opacity: 0.16                   rail alpha
//     live_label: ТРИВОГА             caption of the open wave
//
// WHY A SUBCLASS AND NOT A WRAPPER
//   A wrapper would have to watch the inner card's shadow root and re-insert its
//   parts after every render. A subclass gets Lit's updated() at exactly that
//   moment, so the classes and the caption land in the same frame as the rows.
//   The rows are never moved into wrapper elements: Lit owns their parent, and a
//   wrapper would break its child bookkeeping.
//
// KNOWN LIMIT
//   The rows are found by the class names the base card renders (.item.history,
//   .item-content) and by the state-badge stateObj it passes. A future version of
//   logbook-card can rename them. node ha-mcp/wave-divider-proof.mjs runs the real
//   card in a browser and reports when a wave end loses its caption.
//
// CACHE
//   /local is cached for 31 days, so the resource URL carries the file hash. The
//   open page needs one reload after a new build.

const TAG = 'wave-divider-card';
const BASE = 'multiple-logbook-card';

const DEFAULTS = {
  entity: 'sensor.air_wave_local',
  state: 'idle',
  mode: 'rail',
  thickness: 2,
  opacity: 0.16,
};

// The card speaks the language of the signed-in user: `hass.language` is the
// profile language. Incoming operator messages stay Ukrainian; only the words
// the card prints follow the language. A `divider.live_label` in the config
// still wins, so an older dashboard keeps its own word.
const langOf = (hass) => (String((hass && hass.language) || 'en').toLowerCase().startsWith('uk') ? 'uk' : 'en');
const TEXT = {
  uk: { live: 'ТРИВОГА', clear: 'ВІДБІЙ', ongoing: 'триває', minutes: 'хв', hours: 'год' },
  en: { live: 'AIR ALERT', clear: 'ALL CLEAR', ongoing: 'ongoing', minutes: 'min', hours: 'h' },
};

// The rail is a pseudo-element, so no row is wrapped and nothing is inserted
// between rows except the live caption.
const RAIL_CSS = `
  .item.history {
    position: relative;
    margin-block: 0;
    padding-block: 4px;
    padding-left: 12px;
  }
  .item.history::before {
    content: '';
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    width: var(--wave-rail, 2px);
    background: var(--secondary-text-color, #9e9e9e);
    opacity: var(--wave-rail-opacity, 0.16);
  }
  .item.history.wave-head { margin-top: 16px; }
  .item.history.wave-head-first { margin-top: 4px; }
  .item.history.wave-head .item-icon { display: none; }
  .item.history.wave-head .item-content {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .item.history.wave-head .state {
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--secondary-text-color, #9e9e9e);
  }
  .item.history.wave-head .date { font-size: 0.66rem; }
  .wave-live {
    position: relative;
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 0 0 4px 12px;
  }
  .wave-live::before {
    content: '';
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    width: var(--wave-rail, 2px);
    background: #ff5c5c;
    opacity: 0.8;
  }
  .wave-live .live-state {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #ff8a8a;
  }
  .wave-live .live-meta {
    font-size: 0.66rem;
    color: var(--secondary-text-color, #9e9e9e);
  }
  /* The area line under the reason. */
  .item.history .wave-areas {
    /* Eugene, 2026-10-21: "make the lower line bigger, it is hard to read".
       0.66rem was the caption size, and this line carries places and the
       weapon: it reads better at the body size of the card. */
    font-size: 0.85rem;
    line-height: 1.3;
    margin-top: 2px;
    color: var(--secondary-text-color, #9e9e9e);
  }
  .item.history.wave-live-body::before {
    background: #ff5c5c;
    opacity: 0.8;
  }
  /* The oldest row can be an all-clear whose messages are older than the window.
     It carries no block, so it is hidden and the list simply ends. */
  .item.history.wave-tail { display: none; }
  /* The logbook starts the period with a "state at the window start" row. Its
     time is the window start itself, so it moves forward with the clock and
     repeats the newest state. It is not an event: hide it. */
  .item.history.wave-boundary { display: none; }
  /* A caption whose block kept no visible message has nothing to head. */
  .item.history.wave-empty { display: none; }
  /* A day header with no visible row under it is empty too. */
  .date-separator.wave-empty-day { display: none; }
`;

function formatMinutes(total, text) {
  if (total < 60) return `${total} ${text.minutes}`;
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${hours} ${text.hours} ${rest} ${text.minutes}` : `${hours} ${text.hours}`;
}

// The row text is the operator's sentence, and it names the area before the
// reason. The list is read as a timeline, so the row keeps the reason only.
// Eugene, 2026-10-21: "process messages output, extract only reason".
//
// Two levels, and the order is always the same:
//   1. the danger class, in the big line: Ракетна небезпека, БпЛА, Авіабомба
//   2. the weapon itself, first on the grey line: Бандероль, Шахед, Реактивний
// That way "Бандероль" never stands before "Ракетна небезпека", and every
// drone reads as one type with its own kind under it.
const CLASSES = [
  [/ракетна небезпека|ракетної небезпеки/, 'missile'],
  [/балістик/, 'ballistic'],
  [/авіабомб|габ|каб|умпб/, 'bomb'],
  [/крилат\S*\s+ракет\S*|крилат\S*/, 'cruise'],
  [/бпла|дрон|бпа|реактивн/, 'drone'],
  [/заходи безпеки/, 'security'],
];

const CLASS_LABEL = {
  missile: { uk: 'Ракетна небезпека', en: 'Missile threat' },
  ballistic: { uk: 'Балістика', en: 'Ballistic' },
  bomb: { uk: 'Авіабомба', en: 'Guided bomb' },
  cruise: { uk: 'Крилата ракета', en: 'Cruise missile' },
  drone: { uk: 'БпЛА', en: 'Drone' },
  security: { uk: 'Заходи безпеки', en: 'Security measures' },
};

const SUBTYPES = [
  [/реактивн/, 'jet'],
  // Nicknames: "Герань" and "Мопед" are the same drone as "Шахед".
  [/шахед|шахид|геран\S*|мопед/, 'shahed'],
  [/бандерол/, 'banderol'],
  [/гербер/, 'gerbera'],
  [/кінжал|кинжал/, 'kinzhal'],
  [/іскандер|искандер/, 'iskander'],
  [/циркон/, 'zircon'],
  [/калібр/, 'kalibr'],
  [/х[-\s]?(101|555|59|31|35)/, (m) => `kh-${m[1]}`],
  [/с[-\s]?(300|400)/, (m) => `s-${m[1]}`],
  [/фпв|fpv/, 'fpv'],
];

const SUBTYPE_LABEL = {
  jet: { uk: 'Реактивний', en: 'Jet-powered' },
  shahed: { uk: 'Шахед', en: 'Shahed' },
  banderol: { uk: 'Бандероль', en: 'Banderol' },
  gerbera: { uk: 'Гербера', en: 'Gerbera' },
  kinzhal: { uk: 'Кинжал', en: 'Kinzhal' },
  iskander: { uk: 'Іскандер', en: 'Iskander' },
  zircon: { uk: 'Циркон', en: 'Zircon' },
  kalibr: { uk: 'Калібр', en: 'Kalibr' },
  fpv: { uk: 'FPV', en: 'FPV' },
};

// The sentence often names no weapon, but the entity that reported it does.
// The icons stay as they are, so the grey line carries the type in words.
const MODEL_BY_ENTITY = [
  ['_ballistic', 'ballistic'],
  ['_cruise', 'cruise'],
  ['_gab', 'bomb'],
];

const firstKey = (rules, lower) => {
  for (const [pattern, key] of rules) {
    const match = pattern.exec(lower);
    if (match) return typeof key === 'function' ? key(match) : key;
  }
  return '';
};

// A named weapon decides its own class when the sentence names no class:
// "шахеди з півдня" is a drone wave, "Кинжали" is a missile threat.
const CLASS_BY_SUBTYPE = {
  shahed: 'drone',
  banderol: 'drone',
  gerbera: 'drone',
  fpv: 'drone',
  jet: 'drone',
};

function labelOf(key, lang) {
  if (CLASS_LABEL[key]) return CLASS_LABEL[key][lang];
  if (SUBTYPE_LABEL[key]) return SUBTYPE_LABEL[key][lang];
  const kh = /^kh-(\d+)$/.exec(key);
  if (kh) return lang === 'uk' ? `Х-${kh[1]}` : `Kh-${kh[1]}`;
  const s = /^s-(\d+)$/.exec(key);
  if (s) return lang === 'uk' ? `С-${s[1]}` : `S-${s[1]}`;
  return '';
}

function reasonOf(text, subtypeKey, lang) {
  const named = firstKey(CLASSES, text.toLowerCase());
  if (named) return CLASS_LABEL[named][lang];
  if (subtypeKey) return CLASS_LABEL[CLASS_BY_SUBTYPE[subtypeKey] ?? 'missile'][lang];
  return text;
}

// The weapon, or the kind of the weapon, that the row adds to its reason.
function subtypeKeyOf(text, entityId) {
  const named = firstKey(SUBTYPES, text.toLowerCase());
  if (named) return named;
  const hit = MODEL_BY_ENTITY.find(([end]) => String(entityId ?? '').endsWith(end));
  return hit ? hit[1] : '';
}

// The reason alone does not say where. The area names sit under it in small
// grey text, in the order the sentence gives them. The sentence is cut back to
// its place names: everything that is not a place is dropped first, then the
// area shapes are read out of what is left. A place name starts with a capital,
// so the leftover of a weapon name ("на район") does not read as one.
const NAME = "[А-ЯІЇЄA-Z][А-Яа-яІіЇїЄєA-Za-z'’.-]*";
const AREA_UNIT = new RegExp(
  `м\\.\\s*${NAME}|смт\\.?\\s*${NAME}|с\\.\\s*${NAME}|${NAME}\\s+район|${NAME}\\s+громада`,
  'g',
);
const NOISE = [
  [/тривога по/gi, ' '],
  [/тривога/gi, ' '],
  [/заходи безпеки/gi, ' '],
  [/у вашому напрямку/gi, ' '],
  [/в сторону[^.,;!]*/gi, ' '],
  [/в напрямку[^.,;!]*/gi, ' '],
  [/на місто/gi, ' '],
  [/ще/gi, ' '],
  [/[—–]/g, ' , '],
  [/[!.]/g, ' '],
];

function areasOf(text) {
  // "м. Полтава" would lose its dot to the noise pass, so the abbreviations are
  // parked on a placeholder and the dot is put back before the shapes are read.
  let rest = text.replace(/(^|[\s,])(м|смт|с)\./g, '$1$2\u0001');
  for (const [pattern] of [...CLASSES, ...SUBTYPES]) {
    rest = rest.replace(new RegExp(pattern.source, 'gi'), ' ');
  }
  for (const [pattern, replacement] of NOISE) rest = rest.replace(pattern, replacement);
  rest = rest.replace(/\u0001/g, '.');

  const units = [];
  const seen = new Set();
  for (const match of rest.matchAll(AREA_UNIT)) {
    const unit = match[0].replace(/\s+/g, ' ').trim();
    // "м. Полтава" and "м. Полтави" in one sentence are one place.
    const key = unit.toLowerCase().replace(/[аиуії]$/, '');
    if (seen.has(key)) continue;
    seen.add(key);
    units.push(unit);
  }
  if (units.length) return units.join(', ');
  // No place in a known shape: the grey line stays empty. A guessed remainder
  // read as noise ("Пуски ів з МіГ-31К") on 2026-10-21.
  return '';
}

// ---------------------------------------------------------------------------
// Editor
//
// A card added from the picker starts with getStubConfig(): the six standard
// Wave Poltava entities and the rail settings. The editor then changes the
// entity ids, the period and the rail without YAML.

const EDITOR_TAG = 'wave-divider-card-editor';

const DEFAULT_IDS = {
  wave: 'sensor.air_wave_local',
  drone: 'sensor.air_wave_label_drone',
  ballistic: 'sensor.air_wave_label_ballistic',
  cruise: 'sensor.air_wave_label_cruise',
  gab: 'sensor.air_wave_label_gab',
  other: 'sensor.air_wave_label',
};

const ROW_DEFAULTS = {
  wave: {
    state_map: [
      { value: 'active', label: 'Тривога', icon: 'mdi:alert-octagon', icon_color: '#ff5c5c' },
      { value: 'idle', label: 'Відбій', icon: 'mdi:shield-check', icon_color: '#44739e' },
    ],
    hidden_state: ['active', '—', 'unknown', 'unavailable'],
  },
  drone: {
    state_map: [{ value: '*', icon: 'mdi:drone', icon_color: '#f5a623' }],
    hidden_state: ['—', 'unknown', 'unavailable'],
    minimal_duration: 60,
  },
  ballistic: {
    state_map: [{ value: '*', icon: 'mdi:rocket-launch', icon_color: '#ff5252' }],
    hidden_state: ['—', 'unknown', 'unavailable'],
    minimal_duration: 60,
  },
  cruise: {
    state_map: [{ value: '*', icon: 'mdi:rocket', icon_color: '#ff7043' }],
    hidden_state: ['—', 'unknown', 'unavailable'],
    minimal_duration: 60,
  },
  gab: {
    state_map: [{ value: '*', icon: 'mdi:bomb', icon_color: '#ffa726' }],
    hidden_state: ['—', 'unknown', 'unavailable'],
    minimal_duration: 60,
  },
  other: {
    state_map: [{ value: '*', icon: 'mdi:eye', icon_color: '#f5a623' }],
    hidden_state: ['—', 'unknown', 'unavailable'],
    minimal_duration: 60,
  },
};

const EDITOR_SCHEMA = [
  { name: 'wave', selector: { entity: { domain: 'sensor' } } },
  { name: 'drone', selector: { entity: { domain: 'sensor' } } },
  { name: 'ballistic', selector: { entity: { domain: 'sensor' } } },
  { name: 'cruise', selector: { entity: { domain: 'sensor' } } },
  { name: 'gab', selector: { entity: { domain: 'sensor' } } },
  { name: 'other', selector: { entity: { domain: 'sensor' } } },
  { name: 'hours_to_show', selector: { number: { min: 1, max: 168, step: 1, mode: 'box', unit_of_measurement: 'h' } } },
  { name: 'scroll', selector: { boolean: {} } },
  { name: 'rail_thickness', selector: { number: { min: 1, max: 8, step: 1, mode: 'box', unit_of_measurement: 'px' } } },
  { name: 'rail_opacity', selector: { number: { min: 0, max: 1, step: 0.01, mode: 'box' } } },
];

const EDITOR_LABELS = {
  wave: 'Хвиля (рядок active/idle)',
  drone: 'БпЛА',
  ballistic: 'Балістика',
  cruise: 'Ракети',
  gab: 'КАБ',
  other: 'Інше повідомлення',
  hours_to_show: 'Період, годин',
  scroll: 'Прокрутка',
  rail_thickness: 'Товщина лінії',
  rail_opacity: 'Прозорість лінії',
};

function findEntity(hass, suffix, fallback) {
  const ids = Object.keys((hass && hass.states) || {});
  return ids.find((id) => id === fallback)
    ?? ids.find((id) => id.endsWith(suffix))
    ?? fallback;
}

function stubConfig(hass) {
  const id = (suffix, fallback) => findEntity(hass, suffix, fallback);
  const wave = id('air_wave_local', DEFAULT_IDS.wave);
  return {
    type: TAG,
    hours_to_show: 24,
    scroll: false,
    date_format: 'HH:mm',
    group_by_day: true,
    show: { duration: false, start_date: true, end_date: false, icon: true, state: true, entity_name: false, separator: false },
    no_event: 'Немає подій за цей період',
    entities: [
      { entity: wave, ...ROW_DEFAULTS.wave },
      { entity: id('air_wave_label_drone', DEFAULT_IDS.drone), ...ROW_DEFAULTS.drone },
      { entity: id('air_wave_label_ballistic', DEFAULT_IDS.ballistic), ...ROW_DEFAULTS.ballistic },
      { entity: id('air_wave_label_cruise', DEFAULT_IDS.cruise), ...ROW_DEFAULTS.cruise },
      { entity: id('air_wave_label_gab', DEFAULT_IDS.gab), ...ROW_DEFAULTS.gab },
      { entity: id('air_wave_label', DEFAULT_IDS.other), ...ROW_DEFAULTS.other },
    ],
    divider: { entity: wave, state: 'idle', mode: 'rail', thickness: 2, opacity: 0.16 },
  };
}

class WaveDividerCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    const style = document.createElement('style');
    style.textContent = ':host{display:block}.intro{padding:4px 0 12px;color:var(--secondary-text-color);font-size:14px;line-height:1.4}';
    this.shadowRoot.append(style);
    this._form = null;
  }

  setConfig(config) {
    this._config = config ?? {};
    if (!this._form) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    else this._render();
  }

  _data() {
    const config = this._config ?? {};
    const rows = Array.isArray(config.entities) ? config.entities : [];
    const entity = (needle, fallback) => {
      const row = rows.find((item) => String(item.entity ?? '').includes(needle));
      return row?.entity ?? fallback;
    };
    const generic = rows.find((item) => String(item.entity ?? '').endsWith('air_wave_label'));
    return {
      wave: config.divider?.entity ?? entity('air_wave_local', DEFAULT_IDS.wave),
      drone: entity('air_wave_label_drone', DEFAULT_IDS.drone),
      ballistic: entity('air_wave_label_ballistic', DEFAULT_IDS.ballistic),
      cruise: entity('air_wave_label_cruise', DEFAULT_IDS.cruise),
      gab: entity('air_wave_label_gab', DEFAULT_IDS.gab),
      other: generic?.entity ?? DEFAULT_IDS.other,
      hours_to_show: Number(config.hours_to_show ?? 24),
      scroll: config.scroll === true,
      rail_thickness: Number(config.divider?.thickness ?? 2),
      rail_opacity: Number(config.divider?.opacity ?? 0.16),
    };
  }

  _render() {
    if (!this._hass || !this._config || this._form) return;
    const intro = document.createElement('div');
    intro.className = 'intro';
    intro.textContent = 'Сутності Wave Poltava підставлені автоматично. Змініть їх, якщо перейменували.';
    const form = document.createElement('ha-form');
    form.hass = this._hass;
    form.data = this._data();
    form.schema = EDITOR_SCHEMA;
    form.computeLabel = (schema) => EDITOR_LABELS[schema.name] ?? schema.name;
    form.addEventListener('value-changed', (event) => {
      event.stopPropagation();
      this._changed(event.detail.value);
    });
    this.shadowRoot.append(intro, form);
    this._form = form;
  }

  _changed(data) {
    const config = this._config ?? {};
    const rows = Array.isArray(config.entities) ? config.entities : [];
    const prior = (needle) => rows.find((item) => String(item.entity ?? '').includes(needle)) ?? {};
    const row = (needle, entity, defaults) => ({ ...defaults, ...prior(needle), entity });
    const wave = data.wave || DEFAULT_IDS.wave;
    const generic = rows.find((item) => String(item.entity ?? '').endsWith('air_wave_label')) ?? {};
    const next = {
      ...config,
      type: TAG,
      hours_to_show: Number(data.hours_to_show ?? 24),
      scroll: data.scroll === true,
      entities: [
        row('air_wave_local', wave, ROW_DEFAULTS.wave),
        row('air_wave_label_drone', data.drone || DEFAULT_IDS.drone, ROW_DEFAULTS.drone),
        row('air_wave_label_ballistic', data.ballistic || DEFAULT_IDS.ballistic, ROW_DEFAULTS.ballistic),
        row('air_wave_label_cruise', data.cruise || DEFAULT_IDS.cruise, ROW_DEFAULTS.cruise),
        row('air_wave_label_gab', data.gab || DEFAULT_IDS.gab, ROW_DEFAULTS.gab),
        { ...ROW_DEFAULTS.other, ...generic, entity: data.other || DEFAULT_IDS.other },
      ],
      divider: {
        ...(config.divider ?? {}),
        entity: wave,
        state: config.divider?.state ?? 'idle',
        mode: config.divider?.mode ?? 'rail',
        thickness: Number(data.rail_thickness ?? 2),
        opacity: Number(data.rail_opacity ?? 0.16),
      },
    };
    this._config = next;
    this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: next }, bubbles: true, composed: true }));
  }
}

if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, WaveDividerCardEditor);

function define() {
  const Base = customElements.get(BASE);
  if (!Base) return;

  window.customCards = window.customCards ?? [];
  if (!window.customCards.some((card) => card.type === TAG)) {
    window.customCards.push({
      type: TAG,
      name: 'Wave divider logbook',
      description: 'The multiple logbook card with one rail and a caption per wave.',
      preview: false,
    });
  }
  if (customElements.get(TAG)) return;

  class WaveDividerCard extends Base {
    static getStubConfig(hass) {
      return stubConfig(hass);
    }

    static getConfigElement() {
      return document.createElement(EDITOR_TAG);
    }

    setConfig(config) {
      super.setConfig(config);
      this._divider = { ...DEFAULTS, ...(config.divider ?? {}) };
      this._hours = Number(config.hours_to_show ?? 120);
      this._applyMode();
    }

    connectedCallback() {
      super.connectedCallback?.();
      // The base card leaves the host inline, and a ResizeObserver on an inline
      // box never reports a size: measured 2026-10-18, the pop-up opened at 357 px
      // and the observer still held 0. A block host makes the observer work.
      if (this.renderRoot && !this._style) {
        const style = document.createElement('style');
        style.textContent = ':host{display:block}';
        this.renderRoot.appendChild(style);
        this._style = style;
      }
      this._applyMode();
      if (typeof ResizeObserver === 'undefined') return;
      this._resize?.disconnect();
      this._width = -1;
      this._resize = new ResizeObserver(() => {
        const width = Math.round(this.getBoundingClientRect().width);
        if (width === this._width) return;
        this._width = width;
        this._decorate();
      });
      this._resize.observe(this);
    }

    disconnectedCallback() {
      this._resize?.disconnect();
      this._resize = null;
      super.disconnectedCallback?.();
    }

    updated(changed) {
      super.updated?.(changed);
      this._decorate();
    }

    // Rail width, alpha, and the rule set that draws the rail.
    _applyMode() {
      const { thickness, opacity, mode } = this._divider ?? DEFAULTS;
      this.style.setProperty('--wave-rail', `${thickness}px`);
      this.style.setProperty('--wave-rail-opacity', String(opacity));
      if (this._style) this._style.textContent = `:host{display:block}${mode === 'line' ? '' : RAIL_CSS}`;
    }

    // true when the row is the all-clear that closes a wave.
    _endsWave(row) {
      const badge = row.querySelector('state-badge');
      const stateObj = badge?.stateObj;
      if (!stateObj) return false;
      return stateObj.entity_id === this._divider.entity
        && String(stateObj.state) === this._divider.state;
    }

    // The previous sibling that is a row or a day header, so a stray node does
    // not hide the day break.
    _prevBlock(row) {
      let node = row.previousElementSibling;
      while (node && !node.classList.contains('item') && !node.classList.contains('date-separator')) {
        node = node.previousElementSibling;
      }
      return node;
    }

    _decorate() {
      const root = this.renderRoot;
      if (!root || !this._divider) return;
      for (const old of root.querySelectorAll('.wave-divider, .wave-live, .wave-areas')) old.remove();

      const rows = [...root.querySelectorAll('.item.history')];
      for (const row of rows) {
        row.classList.remove('wave-head', 'wave-head-first', 'wave-live-body', 'wave-tail', 'wave-boundary', 'wave-empty');
      }
      // 20 s covers the gap between the fetch and this render; a real event that
      // close to the window start is rare and ambiguous anyway.
      const windowStart = Date.now() - this._hours * 3600000;
      for (const row of rows) {
        const date = row.querySelector('logbook-date')?.date;
        if (date instanceof Date && Math.abs(date.getTime() - windowStart) < 20000) {
          row.classList.add('wave-boundary');
        }
      }
      if (!rows.length) return;

      if (this._divider.mode === 'line') this._decorateLine(rows);
      else this._decorateRail(rows);
      this._shortenReasons(rows);
      this._addAreas(rows);
      this._hideEmptyDays(root);
    }

    // The base card owns the text node: a replacement node would leave Lit
    // writing into a detached one, so the value is changed in place and the
    // whole sentence goes to the row tooltip. Lit writes the original back on
    // its next render, and the check below reads that as a new message.
    _shortenReasons(rows) {
      this._written = this._written ?? new WeakMap();
      for (const row of rows) {
        if (row.classList.contains('wave-head')) continue;
        const cell = row.querySelector('.item-content > .state');
        if (!cell) continue;
        const node = [...cell.childNodes].find((child) => child.nodeType === 3 && child.nodeValue.trim());
        if (!node) continue;
        if (this._written.get(node) === node.nodeValue) continue;
        const full = node.nodeValue.trim();
        const entityId = row.querySelector('state-badge')?.stateObj?.entity_id;
        // The subtype is worked out here, so the grey line uses the same one.
        const subtypeKey = subtypeKeyOf(full, entityId);
        row._waveSubtype = labelOf(subtypeKey, langOf(this.hass));
        const reason = reasonOf(full, subtypeKey, langOf(this.hass));
        row.title = full;
        if (reason === full) continue;
        node.nodeValue = reason;
        this._written.set(node, reason);
      }
    }

    // The reason alone does not say where. The place names, and the words that
    // say where a threat is heading, go under it in small grey text, taken from
    // the whole sentence the row tooltip keeps.
    _addAreas(rows) {
      for (const row of rows) {
        if (row.classList.contains('wave-head')) continue;
        const content = row.querySelector('.item-content');
        const cell = content?.querySelector('.state');
        if (!content || !cell || !row.title) continue;
        // The type line is dropped when the reason already names it.
        const subtype = row._waveSubtype ?? '';
        const head = subtype && !cell.textContent.includes(subtype) ? subtype : '';
        // Eugene, 2026-10-21: the direction words add nothing, so the line is
        // the weapon and the places only.
        const text = [head, areasOf(row.title)].filter(Boolean).join(' · ');
        if (!text) continue;
        const line = document.createElement('div');
        line.className = 'wave-areas';
        line.textContent = text;
        cell.after(line);
      }
    }

    // A day header whose rows were all hidden would stand alone at the bottom.
    _hideEmptyDays(root) {
      const hidden = ['wave-tail', 'wave-boundary', 'wave-empty'];
      for (const separator of root.querySelectorAll('.date-separator')) {
        separator.classList.remove('wave-empty-day');
        let node = separator.nextElementSibling;
        let hasRow = false;
        while (node && !node.classList.contains('date-separator')) {
          if (node.classList.contains('item') && !hidden.some((c) => node.classList.contains(c))) {
            hasRow = true;
            break;
          }
          node = node.nextElementSibling;
        }
        if (!hasRow) separator.classList.add('wave-empty-day');
      }
    }

    _decorateRail(rows) {
      for (const row of rows) {
        if (!this._endsWave(row)) continue;
        row.classList.add('wave-head');
        // The all-clear caption comes from the card's state_map, which is a
        // config string; the card writes the word itself so it can follow the
        // profile language.
        const head = row.querySelector('.item-content > .state');
        if (head) head.textContent = TEXT[langOf(this.hass)].clear;
        const previous = this._prevBlock(row);
        // The day header already splits, so the first wave of a day starts at
        // once; every other wave gets a gap that breaks the rail.
        if (!previous || !previous.classList.contains('item')) row.classList.add('wave-head-first');
      }

      // A caption with no visible message under it heads nothing: the boundary
      // row is hidden, and a wave whose only row is that boundary must go too.
      const visible = rows.filter((row) => !row.classList.contains('wave-boundary'));
      for (let i = 0; i < visible.length; i += 1) {
        const row = visible[i];
        if (!row.classList.contains('wave-head')) continue;
        const next = visible[i + 1];
        if (!next || next.classList.contains('wave-head')) row.classList.add('wave-empty');
      }

      const last = visible[visible.length - 1];
      if (last && last.classList.contains('wave-head')) last.classList.add('wave-tail');

      if (this._isLive(visible)) {
        for (const row of visible) {
          if (row.classList.contains('wave-head')) break;
          row.classList.add('wave-live-body');
        }
        visible[0].before(this._liveCaption());
      }
    }

    // The open wave has no all-clear row, so the card draws its own caption.
    _isLive(rows) {
      const state = this.hass?.states?.[this._divider.entity]?.state;
      return state === 'active' && !rows[0].classList.contains('wave-head');
    }

    _liveCaption() {
      const caption = document.createElement('div');
      caption.className = 'wave-live';
      const label = document.createElement('span');
      label.className = 'live-state';
      const text = TEXT[langOf(this.hass)];
      label.textContent = this._divider.live_label || text.live;
      const meta = document.createElement('span');
      meta.className = 'live-meta';
      const minutes = this._liveMinutes();
      meta.textContent = minutes == null ? text.ongoing : `${text.ongoing} ${formatMinutes(minutes, text)}`;
      caption.append(label, meta);
      return caption;
    }

    // The caption counts the alert that is running, not the whole wave. One wave
    // can hold an all-clear and a second alert: measured 2026-10-22, our area was
    // clear at 11:42 and red again at 11:56 while the wave had opened at 10:54, so
    // "1 год 12 хв" was 14 minutes of quiet plus two alerts (Eugene: "не може
    // тривога тривати 1 годину"). `local_started_at` dates the running alert; a
    // card in front of an older component falls back to the wave start.
    _liveMinutes() {
      const attrs = this.hass?.states?.[this._divider.entity]?.attributes;
      const start = this._moment(attrs?.local_started_at) ?? this._moment(attrs?.started_at);
      if (start == null) return null;
      return Math.max(0, Math.round((Date.now() - start) / 60000));
    }

    // `local_started_at` is ISO with a zone. The older `started_at` is local time
    // as "2026-10-18 14:43:29": not ISO (no T, no zone), and Safari answers NaN
    // for it, so those parts are read by hand.
    _moment(raw) {
      if (!raw) return null;
      const iso = Date.parse(raw);
      if (Number.isFinite(iso)) return iso;
      const parts = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(raw);
      if (!parts) return null;
      const local = new Date(+parts[1], +parts[2] - 1, +parts[3], +parts[4], +parts[5], +parts[6]).getTime();
      return Number.isFinite(local) ? local : null;
    }

    // The straight-line design, kept for divider.mode: line.
    _decorateLine(rows) {
      let waiting = false;
      for (const row of rows) {
        if (!this._endsWave(row)) continue;
        const previous = this._prevBlock(row);
        if (!previous || !previous.classList.contains('item')) continue;
        const line = this._line(row);
        if (line) {
          row.before(line);
        } else {
          waiting = true;
        }
      }
      // The pop-up lays its cards out inside the opening animation: measured
      // 2026-10-18, the first render had 12 rows and a text column of 0 px, and
      // the host width did not change afterwards, so the ResizeObserver stayed
      // quiet. A short retry draws the lines as soon as the column has a width.
      clearTimeout(this._retry);
      this._retry = null;
      if (waiting && (this._tries ?? 0) < 8) {
        this._tries = (this._tries ?? 0) + 1;
        this._retry = setTimeout(() => { this._retry = null; this._decorate(); }, 150);
      } else if (!waiting) {
        this._tries = 0;
      }
    }

    _line(row) {
      const content = row.querySelector('.item-content');
      if (!content) return null;
      const rowRect = row.getBoundingClientRect();
      const contentRect = content.getBoundingClientRect();
      const width = Math.round(contentRect.width);
      if (width < 40) return null; // the card is hidden or collapsed

      const { thickness, opacity } = this._divider;
      const inset = Math.max(0, Math.round(contentRect.left - rowRect.left));

      const line = document.createElement('div');
      line.className = 'wave-divider';
      line.setAttribute('aria-hidden', 'true');
      line.style.cssText = [
        'display:block',
        'height:0',
        `border-top:${thickness}px solid currentColor`,
        `margin:5px 0 7px ${inset}px`,
        'color:var(--secondary-text-color, #9e9e9e)',
        `opacity:${opacity}`,
        'pointer-events:none',
      ].join(';');
      return line;
    }
  }

  customElements.define(TAG, WaveDividerCard);
}

if (customElements.get(BASE)) define();
else customElements.whenDefined(BASE).then(define);
