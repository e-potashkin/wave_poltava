#!/usr/bin/env python3
"""Test the marker classifier against real messages from the channel.

    python3 tests/test_markers.py

WHY
    The wave layer must decide when a wave starts and ends from the channel's own
    markers. `aerial_danger` matches a narrow set of patterns and misses most real
    messages, so this classifier reads the markers instead.

THE CASES
    Every message below is real, from 2026-10-13 and 14, and every expected
    verdict is the one a person who reads Ukrainian would give it. Several cases
    exist to catch a specific mistake:

      "відбою поки не очікуємо"            a reversal, not a wind-down
      "Якщо нічого не зміниться, очікуємо"  a wind-down, not an end
      "Швидкісних цілей … не фіксуємо"      an end, although it starts with "❗️"
      "канал підтримали 5 людей"            noise, although it names "канал"
      "Полтавська область — в небі чисто"   an end for the oblast

    The file is data. Add a message whenever the channel uses a new phrasing.
"""

import sys

sys.path.insert(0, "custom_components/wave_poltava")

from markers import (  # noqa: E402
    BALLISTIC,
    CONTINUATION,
    CRUISE,
    DRONE,
    END,
    NOISE,
    REVERSAL,
    ROCKET,
    START,
    WIND_DOWN,
    UNKNOWN,
    classify,
)

CASES = [
    # (message, kind, areas, type, note)
    ("🟡Лубенський район — тривога по БпЛА",
     START, ["lubny_raion"], DRONE, "district alert"),
    ("🟡Полтавський район — тривога по БпЛА",
     START, ["poltava_raion"], DRONE, "district alert"),
    ("Полтавський район Кременчуцький район 🔴Ракетна небезпека",
     START, ["poltava_raion", "kremenchuk_raion"], ROCKET, "rocket danger, two districts"),
    ("Полтавський район Миргородський район Кременчуцький район Лубенський район 🔴Ракетна небезпека",
     START, ["poltava_raion", "myrhorod_raion", "kremenchuk_raion", "lubny_raion"], ROCKET,
     "rocket danger, four districts, in the order the post names them"),
    ("⚠️Загроза застосування балістичного озброєння з Брянської області",
     START, ["bryansk_oblast"], BALLISTIC, "ballistic, launch region"),
    ("⚠️Загроза застосування балістичного озброєння з Курської області",
     START, ["kursk_oblast"], BALLISTIC, "ballistic, launch region"),
    ("🔴Фіксації груп поршневих БпЛА в сторону Полтавської області від Харківської області.",
     START, ["poltava_oblast", "kharkiv_oblast"], DRONE, "the 9-drone raid the parser missed"),
    ("❗️Фіксації реактивних БпЛА від Дніпропетровської області в сторону Кобеляцького району.",
     START, ["dnipro_oblast", "kobeliaky_raion"], DRONE, "jet drones inbound"),
    ("❗️Фіксації мКР «Бандероль» в напрямку Полтавської області від Сумської області.",
     START, ["poltava_oblast", "sumy_oblast"], CRUISE, "cruise missiles"),
    ("❗️Повз Кременчуцький НПЗ прольоти 2од. реактивних БпЛА на північний-захід.",
     START, ["kremenchuk_raion"], DRONE, "jet drones passing an industrial site"),
    ("🟡Полтавський район — тривога по БпЛА\n\n🟡Кременчуцький район — тривога по БпЛА",
     START, ["poltava_raion", "kremenchuk_raion"], DRONE, "two districts, one post"),

    # -- continuation ----------------------------------------------------
    ("Будуть йти за одним маршрутом.",
     CONTINUATION, [], UNKNOWN, "route, no area"),
    ("⚠️Летить від 6од.",
     CONTINUATION, [], UNKNOWN, "count, no area"),
    ("⚠️Вже 9од. БпЛА, попередньо «Герань-2»",
     CONTINUATION, [], DRONE, "count grew, type named"),
    ("В сторону Чутівського району.",
     CONTINUATION, ["chutove_raion"], UNKNOWN, "route, district named"),
    ("Дані БпЛА продовжують рух уздовж лінії розмежування Полтавської та Харківської областей на південь.",
     CONTINUATION, ["poltava_oblast", "kharkiv_oblast"], DRONE, "still moving"),
    ("Пройшли від околиць м. Кобеляки і далі через Козельщинський район і далі через північніше с. Великі Кринки, Глобинський район.",
     CONTINUATION, ["kobeliaky_raion", "kozelshchyna_raion", "hlobyne_raion"], UNKNOWN, "moved on"),
    ("Глобинський район В небі 2 реактивних БпЛА Курс — Черкаська область.",
     START, ["hlobyne_raion", "cherkasy_oblast"], DRONE, "drones overhead, course given"),
    ("Уздовж лінії розмежування Сумської та Полтавської областей фіксації мКР «Бандероль» західним курсом.",
     START, ["sumy_oblast", "poltava_oblast"], CRUISE,
     "cruise missiles, western course; areas in the order the post names them"),
    ("❗️2 мКР. Курсують в сторону Роменського району Сумської області.",
     START, ["romny_raion", "sumy_oblast"], CRUISE,
     "a cruise-missile contact with a count, even though it also gives a course"),
    # "мкр." in an address is a micro-district, not a cruise missile. A
    # case-blind "мкр" pattern typed both of these as CRUISE, and the card draws
    # that row with the rocket glyph, so a drone report showed a rocket
    # (Eugene, 2026-10-16).
    ("м. Полтава\nмкр. Рибці\nКиївський район\nБув проліт БпЛА за місто.",
     CONTINUATION, ["poltava_city"], DRONE, "micro-district, not a cruise missile"),
    ("БпЛА далі в сторону мкр. Сади-1 Шевченківський район м. Полтава",
     CONTINUATION, ["poltava_city"], DRONE, "micro-district, not a cruise missile"),
    ("Приблизно в сторону смт. Градизьк, Глобинський район. Йдуть високо.",
     CONTINUATION, ["hlobyne_raion"], UNKNOWN, "course and altitude"),

    # -- wind-down, and the reversal that cancels it ---------------------
    ("🟢Якщо нічого не зміниться, очікуємо на відбій ракетної небезпеки.",
     WIND_DOWN, [], ROCKET, "wind-down, not an end"),
    ("🟢Полтавський район — якщо нічого не зміниться, очікуйте на відбій тривоги по БпЛА.",
     WIND_DOWN, ["poltava_raion"], DRONE, "wind-down, district named"),
    ("Полтавський район — відбою поки не очікуємо. Є нові фіксації від Дніпропетровської області.",
     REVERSAL, ["poltava_raion", "dnipro_oblast"], UNKNOWN,
     "the wind-down is cancelled; the type is in the earlier post"),

    # -- ends ------------------------------------------------------------
    ("Полтавський район  Відбій тривоги по БпЛА",
     END, ["poltava_raion"], DRONE, "one district clears"),
    ("Кременчуцький район  Відбій тривоги по БпЛА",
     END, ["kremenchuk_raion"], DRONE, "one district clears"),
    ("Кременчуцький район Лубенський район  Відбій тривоги по БпЛА",
     END, ["kremenchuk_raion", "lubny_raion"], DRONE, "two districts clear"),
    ("Полтавський район Кременчуцький район  Відбій ракетної небезпеки",
     END, ["poltava_raion", "kremenchuk_raion"], ROCKET, "rocket alert over"),
    ("Полтавський район Миргородський район Кременчуцький район Лубенський район Відбій ракетної небезпеки",
     END, ["poltava_raion", "myrhorod_raion", "kremenchuk_raion", "lubny_raion"], ROCKET,
     "rocket alert over, four districts"),
    ("🟢Відбій загрози застосування балістичного озброєння.",
     END, [], BALLISTIC, "ballistic threat over"),
    ("🟢Полтавська область — в небі чисто.",
     END, ["poltava_oblast"], UNKNOWN, "the sky is clear, region-wide"),
    # "та околиці" is the city AND its surroundings, so the all-clear covers the
    # raion and the hromada too. Before 2026-10-14 the classifier named the city
    # alone, the raion stayed under alert for the rest of the wave, and the card
    # kept a red row through the channel's own all-clear.
    ("м. Полтава та околиціВідбій уваги по БпЛАНебезпеки минула.Підписатися на канал",
     END, ["poltava_city", "poltava_raion", "poltava_rural"], DRONE, "city clears"),
    ("Миргородський районЛубенський район Загроз не спостерігаємо.🟢По ракетній був відбій.",
     END, ["myrhorod_raion", "lubny_raion"], ROCKET, "nothing observed"),
    ("м. Полтава, м. Кременчук, м. Лубни🟢Не спостерігаємо загроз для вказаних міст.",
     END, ["poltava_city", "kremenchuk_raion", "lubny_raion"], UNKNOWN, "cities clear"),
    ("м. Полтава та околиці «Уваги по БпЛА» не оголошувалось.📡Фіксацій не спостерігаємо.",
     END, ["poltava_city", "poltava_raion", "poltava_rural"], DRONE, "no alert was declared"),
    ("❗️Швидкісних цілей в напрямку Полтавської області наразі не фіксуємо.",
     END, ["poltava_oblast"], UNKNOWN, "nothing recorded, the false positive of 12:40"),

    # The channel writes an all-clear with no space after the district name.
    # Python's \b does not agree with Cyrillic here, so the first version of the
    # classifier read these as noise and no wave would ever close.
    ("Лубенський районКременчуцький районВідбій тривоги по БпЛА",
     END, ["lubny_raion", "kremenchuk_raion"], DRONE, "no space before Відбій"),
    ("Полтавський районМиргородський район Лубенський районКременчуцький районВідбій тривоги по БпЛА",
     END, ["poltava_raion", "myrhorod_raion", "lubny_raion", "kremenchuk_raion"], DRONE,
     "four districts, no spaces"),
    ("Полтавський районРакетна небезпека",
     START, ["poltava_raion"], ROCKET, "no space before the marker, and a start"),
    ("Кременчуцький район Тривога по БпЛА превентивна.",
     START, ["kremenchuk_raion"], DRONE, "preventive alert"),
    ("селище Оржиця та найближчі населені пункти Через вас прольоти реактивних БпЛА",
     CONTINUATION, ["orhzhytsia_raion"], DRONE, "no marker emoji, still a continuation"),
    ("Даний БпЛА більше не відстежується.",
     END, [], DRONE, "tracking ended"),

    ("Полтавська областьВся територія Без фіксацій БпЛА",
     CONTINUATION, ["poltava_oblast"], DRONE, "a status line, not a new alert"),
    ("Станом на зараз по фіксаціях в області:1 поршневий БпЛА в сторону м. Гребінка.",
     CONTINUATION, [], DRONE, "a digest; Hrebinka is outside the city"),

    ("🚨⚠️Пуски ударних БпЛА з Курської області",
     START, ["kursk_oblast"], DRONE, "an announcement of launches"),

    # -- noise -----------------------------------------------------------
    ("🫡Станом на зараз канал підтримали 5 людей, щиро дякуємо! Друзі, останнім часом підтримки каналу стало значно менше.",
     NOISE, [], UNKNOWN, "donation post"),
    ("Друзі, нагадуємо, що адміністрація цього каналу моніторить повітряний простір області 24/7. 4441111143550592",
     NOISE, [], UNKNOWN, "announcement with a card number, no area named"),
    ("🫡Станом на зараз канал підтримали лише 2 людини, щиро дякуємо!",
     NOISE, [], UNKNOWN, "donation post"),
    # -- 2026-10-21: phrases the corpus of 1000 messages turned up ---------
    # Counted over 2026-10-09..21. Each of these was "no marker" before.
    ("БпЛА продовжує рух на с. Щербані, Полтавський район.",
     CONTINUATION, ["poltava_raion"], DRONE, "singular «продовжує рух»"),
    ("м. Миргород Реактивний БпЛА в небі.",
     CONTINUATION, ["myrhorod_city", "myrhorod_raion"], DRONE, "«БпЛА в небі», the noun first"),
    ("Реактивний БпЛА на вас з півночі.",
     CONTINUATION, [], DRONE, "«на вас» instead of «в напрямку»"),
    ("БпЛА через с. Ряська, Машівський район вийшов у Дніпропетровську область.",
     CONTINUATION, ["dnipro_oblast"], DRONE, "«вийшов у» another oblast"),
    ("Даний реактивний БпЛА вилітає у Черкаську область через Глобинський район.",
     CONTINUATION, ["cherkasy_oblast", "hlobyne_raion"], DRONE, "«вилітає у», not «вийшов»"),
    ("І далі пройшов повз аеропорт «Полтава» в сторону Новосанжарського району.",
     CONTINUATION, [], UNKNOWN, "«далі», «повз», a raion outside the city"),
    ("Котелевський район Зайшов реактивний БпЛА",
     START, [], DRONE, "«зайшов» outside Poltava city, so no area"),
    ("м. Кременчук Крюківський район Заходить реактивний БпЛА з півдня!",
     START, ["kremenchuk_raion"], DRONE, "«заходить», Kremenchuk is still mapped"),
    ("м. Полтава Подільський район Заходять ракети!",
     START, ["poltava_city"], ROCKET, "«Заходять ракети»"),
    ("Фіксація поблизу смт. Градизьк, Глобинський район. Низько.",
     START, ["hlobyne_raion"], UNKNOWN, "a fixation without the word «БпЛА»"),
    ("Полтавська область ⚠️Фіксації 9од. БпЛА над регіоном.",
     START, ["poltava_oblast"], DRONE, "«Фіксації 9од.», a count between the words"),
    ("м. Карлівка Карлівський район Підліт реактивного БпЛА.",
     START, [], DRONE, "«Підліт» outside Poltava city, so no area"),
    ("Кременчуцький район Фіксацій не спостерігаємо. Будьте обачні — можлива поява 1 БпЛА.",
     CONTINUATION, ["kremenchuk_raion"], DRONE, "an all-clear taken back in the same breath"),
    ("Гарні новини: Станом на зараз припинилися фіксації від Харківської області.",
     END, ["kharkiv_oblast"], UNKNOWN, "«припинилися фіксації»"),
    # -- the three districts of Poltava city, 2026-10-21 -------------------
    ("м. Полтава Київський район ❗️Реактивний БпЛА у вашому напрямку з півночі!",
     START, ["poltava_city"], DRONE, "a Poltava city district counts as the city"),
    ("м. Полтава Подільський район Уздовж траси мКР «Бандероль» на місто.",
     CONTINUATION, ["poltava_city"], CRUISE, "another city district"),
    ("м. Полтава Шевченківський район Реактивний БпЛА у вашу сторону від с. Щербані, Полтавський район.",
     CONTINUATION, ["poltava_city", "poltava_raion"], DRONE, "a city district plus the raion"),
]

failures = []
for message, kind, areas, type_name, note in CASES:
    got = classify(message)
    ok = got.kind == kind and got.areas == areas and got.type == type_name
    print("%-4s %-13s %-46s %s" % ("ok" if ok else "FAIL", got.kind, note, message[:56]))
    if not ok:
        failures.append((message, kind, areas, type_name, got))

print("")
print("cases: %d" % len(CASES))
if failures:
    print("FAILURES: %d" % len(failures))
    for message, kind, areas, type_name, got in failures:
        print("\n  message : %s" % message[:90])
        print("  want    : %s %s %s" % (kind, areas, type_name))
        print("  got     : %s %s %s" % (got.kind, got.areas, got.type))
        print("  reason  : %s" % got.reason)
    sys.exit(1)
print("all %d messages classified as a person would" % len(CASES))
