# Wave Poltava

Air-raid monitor for Poltava oblast in one Home Assistant integration: the
channel feed, the wave, the reason rows and the dashboard card.

```
  Telegram preview             Wave Poltava                Home Assistant
  ┌──────────────┐            ┌─────────────────┐         ┌────────────────┐
  │ monitoringplt│─ every 30s▶│ feed parser     │────────▶│ wave sensors   │
  │ public page  │            │ marker classify │         │ local alert    │
  └──────────────┘            │ wave tracker    │         │ reason rows    │
                              │ .storage record │         │ bundled card   │
                              └─────────────────┘         └────────────────┘
```

## Screenshots

| Live alert | After the all-clear |
| --- | --- |
| ![Live alert](docs/wave-alert.png) | ![After the all-clear](docs/wave-clear.png) |

Both are the activity card on a phone. The red rail and the `ТРИВОГА` caption
belong to the alert that is running. Every finished wave starts with a
`ВІДБІЙ` caption on the all-clear row.

## Why it exists

1. The feed is fetched and parsed here. No `rest` sensor, no `scrape` sensor and
   no parser integration is needed.
2. The channel's own words decide when a wave starts and ends. The classifier
   reads marks such as `тривога по БпЛА`, `відбій` and `очікуємо на відбій`.
3. The wave is stored in `.storage`. A restart does not lose a running alert.
4. The card ships inside the integration and is loaded on every page. A HACS
   install does not need a second repository or a manual `/local` copy.

## Entities

| Entity | State | Meaning |
| --- | --- | --- |
| `sensor.air_wave` | `active` / `idle` | the wave |
| `sensor.air_wave_local` | `active` / `idle` | Poltava city, raion or hromada |
| `sensor.air_wave_started` | timestamp | when the wave started |
| `sensor.air_wave_ended` | timestamp | when it ended |
| `sensor.air_wave_duration` | minutes | how long it lasted |
| `sensor.air_wave_label` | text / `—` | the channel's words, untyped |
| `sensor.air_wave_label_drone` | text / `—` | a drone message |
| `sensor.air_wave_label_cruise` | text / `—` | a cruise or generic missile message |
| `sensor.air_wave_label_ballistic` | text / `—` | a ballistic message |
| `sensor.air_wave_label_gab` | text / `—` | a guided-bomb message |
| `binary_sensor.air_threat_local_alert` | `on` / `off` | our area is under alert |
| `sensor.monitoring_poltavshchina_text` | text | newest post, for diagnostics |

Every wave entity carries the same attributes: `wave`, `areas`, `cleared`,
`last_message`, `last_event_type`, `message_count`, `release_after_minutes`,
`waves_today`, `messages_today` and `reason`.

`sensor.air_wave_local` also carries `local_started_at`, `local_last_at` and
`local_cleared_at`. The card uses `local_started_at` for the running alert time.

## Card

`custom:wave-divider-card` is served from the integration. It is the logbook
card with one rail per wave, a `ТРИВОГА` caption while our area is under alert,
and a `ВІДБІЙ` caption on the all-clear row.

The card has one frontend dependency: `custom:multiple-logbook-card` from
[logbook-card](https://github.com/royto/logbook-card). Install it with HACS. The
other two bundled modules, `i18n-card` and `i18n-chrome`, have no dependency.

The card has a visual editor. Add it from the card picker, then change the six
entities, the period, the scroll and the rail thickness or opacity. The default
config already uses the six `air_wave` sensors, so a card added from the picker
works at once.

## Install

### HACS, as a custom repository

1. HACS, three-dot menu, **Custom repositories**.
2. Add `https://github.com/e-potashkin/wave_poltava`, category **Integration**.
3. Install **Wave Poltava**, then restart Home Assistant.
4. Add the integration in **Settings → Devices & services → Add integration**.
5. Make sure `logbook-card` is installed for the dashboard card.

### Manually

Copy `custom_components/wave_poltava/` into your `config` directory, so that
`config/custom_components/wave_poltava/manifest.json` exists, then restart.

## Options

**Settings → Devices & services → Wave Poltava → Configure** changes one value:

| Option | Default | Meaning |
| --- | --- | --- |
| Release after | 30 min | silence after the last message that ends a wave |

The release delay is not the length of a wave. Every new message moves the
deadline, so a live raid can hold a wave open for hours.

## What counts as ours

The red row follows `poltava_city`, `poltava_raion` and `poltava_rural`. A
message that names only `Полтавська область` does not light it: the oblast is a
different district, and the channel clears one district at a time.

The list lives in `const.py` (`LOCAL_AREAS`).

## Data source

`https://telegram.me/s/monitoringplt` — the public preview of the
**Моніторинг Полтавщина** channel. The integration reads the last twenty-odd
posts, processes only a post id greater than the stored one, and keeps the line
breaks the channel writes.

## Tests

```
python3 tests/test_feed.py
python3 tests/test_coordinator.py
python3 tests/test_markers.py
python3 tests/test_districts.py
python3 tests/test_markers_flow.py
python3 tests/test_tracker.py
```

The tests use no Home Assistant. They read a saved preview page, 67 real
channel messages and the wave scenarios.

## Limits

- The preview page shows the last twenty-odd posts. A downtime longer than that
  loses the posts in between, but the stored wave still resumes.
- The parser follows the page markup. If Telegram changes the class names,
  `feed.py` needs a new pattern. The feed sensor's `feed_error` attribute says
  when the page stops parsing.
- The card is a subclass of `logbook-card` and finds rows by the base card's
  class names. A base-card update can break the rail and the captions.

## License

MIT. Copyright (c) 2026 Eugene Potashkin.
