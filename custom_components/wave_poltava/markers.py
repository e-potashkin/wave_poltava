"""Read the Poltava monitoring channel's own markers.

The channel marks the start and the end of an alert in words. This module turns
one message into those markers, so the wave layer does not depend on guessing.

    >>> classify("🟡Лубенський район — тривога по БпЛА").kind
    'start'
    >>> classify("Полтавський район  Відбій тривоги по БпЛА").kind
    'end'

WHY THIS EXISTS
    `aerial_danger` matches a narrow set of patterns and misses most of the
    channel's real messages. Measured 2026-10-14: the channel reported a group of
    piston-engine drones inbound at 10:48, said "Вже 9од." at 11:08, and the
    parser matched neither, so the dashboard stayed quiet while nine drones
    crossed the region.

THE GRAMMAR
    Every message is one of six kinds. The lists are closed: each kind uses a
    fixed set of phrasings, which is why a rule engine is enough and a model is
    not.

        start         an alert begins, with the areas named
        continuation  the same alert continues: counts, routes, headings
        wind_down     the channel expects an end soon. NOT an end
        reversal      the channel cancels a wind-down
        end           an alert is over for the named areas
        noise         donations and announcements

    Order matters. A reversal contains "очікуємо", and an end contains "відбій",
    so the reversal is tested first.

AREAS
    An alert belongs to districts, not to the region. The channel clears one
    district while another is still under alert, so the areas are extracted and
    returned as canonical keys.

This module imports nothing outside the standard library.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# -- kinds ---------------------------------------------------------------

START = "start"
CONTINUATION = "continuation"
WIND_DOWN = "wind_down"
REVERSAL = "reversal"
END = "end"
NOISE = "noise"

# -- threat types --------------------------------------------------------

DRONE = "drone"
ROCKET = "rocket"
CRUISE = "cruise"
BALLISTIC = "ballistic"
GAB = "gab"
UNKNOWN = "unknown"

# -- areas ---------------------------------------------------------------
#
# One canonical key per district, with the spellings the channel uses. The order
# of this list is the order of the output, so the region comes first in the
# common case where the message names it and its districts together.

# Python's \b does not agree with Cyrillic in this build, and the channel runs
# words together, so a boundary is needed on ONE side only.
#
#   "Лубенський районКременчуцький районВідбій тривоги"
#
# The district name touches the marker with no space. A left boundary rejects
# that message, which is what the first two attempts at this did: the classifier
# read every all-clear as noise, so no wave could ever close.
#
# A right boundary is still needed, and it is what separates "відбій" from
# "відбою" and "БпЛА" from "БпЛАми".
_WORD_CHARS = "а-яіїєґА-ЯІЇЄҐ"


def _wb(pattern: str) -> str:
    """Add a Cyrillic-aware boundary on the right."""
    return pattern + "(?![" + _WORD_CHARS + r"])"


AREAS: list[tuple[str, str, str]] = [
    # key, display name, pattern
    #
    # The patterns end in a STEM, not in a nominative form. Ukrainian declines
    # the adjective, so a pattern that ends in "-к" does not match "-цький":
    # the first version of this table used "Кременчук" and missed
    # "Кременчуцький НПЗ". Stems match both "Кременчук" and "Кременчуцький".
    #
    # An oblast in a list of two is written once with its noun: "Сумської та
    # Полтавської областей". The adjective-only alternatives catch that.
    ("poltava_oblast", "Полтавська область",
     r"Полтавськ\w*\s+област|Полтавськ\w*\s+та|Полтавщин"),
    ("poltava_city", "м. Полтава",
     # The city has three districts, and the channel names them: "м. Полтава
     # Подільський район Заходять ракети!". The lookahead keeps the same names
     # in Kyiv and Kharkiv out of the match.
     r"м\.\s*Полтав|Полтав[аи]\s+та\s+околиц"
     r"|(?=[\s\S]*Полтав)(?:Київськ|Подільськ|Шевченківськ)\w*\s+район"),
    ("poltava_raion", "Полтавський район", r"Полтавськ\w*\s+район"),
    ("kremenchuk_raion", "Кременчуцький район", r"Кременчуц\w*|Кременчук"),
    ("lubny_raion", "Лубенський район", r"Лубенськ\w*\s+район|" + _wb(r"Лубн\w*")),
    ("myrhorod_raion", "Миргородський район", r"Миргородськ\w*\s+район|Миргород"),
    ("poltava_rural", "Полтавська громада", r"Полтавськ\w*\s+громад"),
    ("kobeliaky_raion", "Кобеляцький район", r"Кобеляц\w*\s+район|" + _wb(r"Кобеляк\w*")),
    ("kozelshchyna_raion", "Козельщинський район", r"Козельщин\w*"),
    ("hlobyne_raion", "Глобинський район", r"Глобинськ\w*\s+район|" + _wb(r"Глобин\w*") + r"|Градизьк"),
    ("semenivka_raion", "Семенівський район", r"Семенівськ\w*"),
    ("orhzhytsia_raion", "Оржицький район", r"Оржиц\w*"),
    ("chutove_raion", "Чутівський район", r"Чутівськ\w*\s+район|" + _wb(r"Чутов\w*")),
    ("reshetylivka_raion", "Решетилівський район", r"Решетилів\w*"),
    ("zinkiv_raion", "Зіньківський район", r"Зіньків\w*"),
    ("hadiach_raion", "Гадяцький район", r"Гадяц\w*|Гадяч"),
    ("lokhvytsia_raion", "Лохвицький район", r"Лохвиц\w*"),
    ("myrhorod_city", "м. Миргород", r"м\.\s*Миргород"),
    ("sumy_oblast", "Сумська область",
     r"Сумськ\w*\s+област|Сумськ\w*\s+та"),
    ("romny_raion", "Роменський район", r"Роменськ\w*\s+район|" + _wb(r"Ромен\w*")),
    ("kharkiv_oblast", "Харківська область",
     r"Харківськ\w*\s+област|Харківськ\w*\s+та"),
    ("dnipro_oblast", "Дніпропетровська область", r"Дніпропетровськ\w*\s+област"),
    ("cherkasy_oblast", "Черкаська область", r"Черкаськ\w*\s+област"),
    ("bryansk_oblast", "Брянська область", r"Брянськ\w*\s+област"),
    ("kursk_oblast", "Курська область", r"Курськ\w*\s+област"),
]

# -- the phrase lists ----------------------------------------------------

# Tested before everything else: a reversal borrows the words of a wind-down.
REVERSAL_PATTERNS = [
    r"відбою\s+поки\s+не\s+очікуємо",
    r"не\s+очікуємо\s+відбою",
    r"є\s+нові\s+фіксації",
]

WIND_DOWN_PATTERNS = [
    r"очікуємо\s+на\s+відбій",
    r"очікуйте\s+на\s+відбій",
    r"якщо\s+нічого\s+не\s+зміниться",
]

END_PATTERNS = [
    _wb(r"відбій"),
    _wb(r"ідбій"),
    r"більше\s+не\s+відстеж",
    r"не\s+відстежується",
    r"покидає\s+нашу\s+область",
    r"покида\w*\s+межі",
    r"припинилися\s+фіксації",
    r"небезпека\s+минул",
    r"небезпеки\s+минул",
    r"в\s+небі\s+чисто",
    r"загроз\s+не\s+спостеріга",
    r"не\s+спостерігаємо\s+загроз",
    r"не\s+фіксуємо",
    r"фіксацій\s+не\s+спостеріга",
    r"не\s+оголошувалось",
]

# A message can report a lost track and still warn that the target may appear:
# "мКР «Бандероль» локаційно не відстежується, можлива поява на наднизькій
# висоті!" is a warning, not an all-clear. An end phrase is ignored when one of
# these is present.
UNCERTAIN_PATTERNS = [
    r"можлив\w*\s+появ",
    r"можлив\w*\s+з\W?яв",
    r"можливе\s+застосування",
    r"можуть\s+з\W?явитися",
]

START_PATTERNS = [
    r"тривога\s+по\s+бпла",
    r"повітрян\w*\s+тривог",
    r"увага\s+по\s+бпла",
    r"ракетна\s+небезпека|ракетної\s+небезпеки|оголошено\s+ракетн",
    r"загроза\s+застосування\s+балістичн",
    r"балістичн\w*\s+озброєння",
    r"фіксаці\w*\s+(груп\s+)?(поршнев\w*|реактивн\w*|невстановлен\w*|мопед\w*)?\s*бпла",
    r"фіксаці\w*\s+мкр",
    r"\d+\s*мкр\b",
    r"\d+\s*кр\b",
    r"фіксаці\w*\s+кр\b",
    r"прольоти?\s+\d*\s*од",
    r"в\s+небі\s+\d+\s+реактивних",
    r"в\s+небі\s+(\d+\s*)?(реактивн\w*|поршнев\w*)?\s*бпла",
    r"фіксація\s+(поршнев\w*|реактивн\w*|невстановлен\w*)?\s*бпла",
    r"фіксація\s+чергового",
    r"заходи\s+безпеки",
    r"реактивний\s+бпла\s+у\s+вашому\s+напрямку",
    r"у\s+ваш(ому|у)\s+напрямку",
    r"пуски?\s+.*бпла",
    r"пуски?\s+.*ракет",
    r"тривога\s+по\s+бпла\s+превентивна",
    r"курс\w*\s*—",
    r"курс\s+на\s+",
    # Counted over 1000 messages, 2026-10-09..21: "Заходить реактивний БпЛА",
    # "Зайшов реактивний БпЛА", "Фіксація поблизу смт. Градизьк",
    # "Фіксації 5од. БпЛА над регіоном", "Ворожий реактивний БпЛА влучив".
    r"заход\w*\s+(ворож\w*\s+)?(реактивн\w*\s+)?бпла",
    r"заходять\s+ракет",
    r"зайш\w*\s+(ворож\w*\s+)?(реактивн\w*\s+)?бпла",
    r"фіксаці\w*\s+поблизу",
    r"фіксаці\w*\s+\d+\s*од",
    r"влучан\w*|влучив|влучила|влучило",
    r"ракет\w*\s+у\s+те\s+саме",
    r"підліт",
    r"робота\s+мвг",
    r"можлив\w*\s+ворож\w*",
]

CONTINUATION_PATTERNS = [
    _wb(r"летить"),
    _wb(r"вже\s+\d+\s*од"),
    _wb(r"від\s+\d+\s*од"),
    r"в\s+сторону\s+\w+",
    r"продовж\w*\s+рух",
    _wb(r"пройшли"),
    r"будуть\s+йти",
    r"західним\s+курсом",
    r"східним\s+курсом",
    r"північн\w*\s+курсом",
    r"південн\w*\s+курсом",
    r"на\s+північ",
    r"на\s+південь",
    r"на\s+захід",
    r"на\s+схід",
    r"йдуть\s+високо",
    r"\bпроліт\b",
    r"\bпрольоти\b",
    r"змін\w*\s+курс",
    r"маневрує",
    r"розвернувся",
    r"підлітає",
    r"прямує",
    r"курсує",
    r"локаційно\s+не",
    # "далі на Полтавський район", "далі через околиці",
    # "БпЛА в небі", "БпЛА над селом", "вийшов у Дніпропетровську область".
    r"далі\s+(на|в|у|через)\s",
    r"\bпроліта\w*",
    r"вийш\w*\s+у\s",
    r"бпла\s+(далі\s+)?(в\s+небі|над\s)",
    r"бпла\s+на\s+",
    r"\bйде\s+(від|на|у)\s",
    r"вже\s+над\s",
    r"пройш\w*\s+повз",
    r"декілька\s+бпла",
    r"виліт\w*|вилет\w*",
    r"пройш\w*\s+через",
    r"у\s+вашу\s+сторону",
    r"(з|зі)\s+(східн|західн|північн|південн)\w*\s+сторони",
    r"\d+\s+(поршнев|реактивн)\w*\s+бпла",
    r"в\s+межах\s+полтавськ",
    r"без\s+змін",
    r"кружляє",
    r"за\s+цим\s+маршрутом",
    r"за\s+маршрутом",
    r"уздовж\s+траси",
    r"скинув",
    r"відстежується",
    r"по\s+фіксаціях\s+в\s+області",
    r"без\s+фіксацій",
    r"вся\s+територія",
]

TYPE_PATTERNS = [
    # "мКР" is the channel's shorthand for cruise missiles: "2 мКР", "мКР
    # «Бандероль»". It is matched CASE-SENSITIVELY, and that is the whole point
    # of this alternative. Written in lower case, "мкр." is the abbreviation for
    # "мікрорайон" in an address, so a case-blind "мкр" typed every drone report
    # that named a micro-district as a cruise missile:
    #
    #   м. Полтава мкр. Рибці Київський район Був проліт БпЛА за місто.
    #
    # The card draws the cruise row with the rocket glyph, so a drone wave showed
    # a rocket next to a drone message (Eugene, 2026-10-16, 18:20). The channel
    # writes the missile as "мКР" in all four measured posts and the district as
    # "мкр." in both measured addresses.
    (CRUISE, [_wb(r"(?-i:мКР|МКР)"), r"крилат\w*\s+ракет", r"бандероль"]),
    (BALLISTIC, [r"балістичн", r"\bіскандер", r"кинджал"]),
    (GAB, [r"\bкаб\b", r"керован\w*\s+авіабомб"]),
    # \b on every alternative: a bare "дрон" also matches inside
    # "Дніпропетровської", which typed that message as a drone report.
    (DRONE, [r"бпла", _wb(r"дрони?"), _wb(r"дронів"), r"герань", r"шахед", r"мопед",
             r"реактивн\w*\s+бпла"]),
    (ROCKET, [r"ракетн\w*\s+небезпек", r"\bракет"]),
]


@dataclass
class Marker:
    """What one message says, in the channel's own terms."""

    kind: str
    areas: list[str] = field(default_factory=list)
    type: str = UNKNOWN
    reason: str = ""
    text: str = ""

    @property
    def area_names(self) -> list[str]:
        names = {key: name for key, name, _ in AREAS}
        return [names.get(key, key) for key in self.areas]

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "areas": self.areas,
            "type": self.type,
            "reason": self.reason,
        }


# A Cyrillic-aware word boundary. Python's \b and Cyrillic disagree in this
# build: re.search(_wb(r"відбій"), "районВідбій тривоги") returns None, while the
# same pattern without the boundaries matches. The channel writes all-clears with
# no space after the district name, so every such message was missed.
_WORD_CHARS = "а-яіїєґА-ЯІЇЄҐ"
_WORD = r"(?<![" + _WORD_CHARS + r"])%s(?![" + _WORD_CHARS + r"])"


def _wb(pattern: str) -> str:
    """Wrap a pattern in Cyrillic-aware word boundaries."""
    return _WORD % pattern


def _search(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return pattern
    return None


# "м. Полтава та околиці" is the city AND its surroundings. The channel writes one
# phrase for both, and the classifier mapped it to the city alone, so an all-clear
# cleared the city while the raion stayed under alert for ever. On 2026-10-14 at
# 20:50 the channel posted that all-clear and the card kept a red row through it.
NEIGHBOURS: dict[str, tuple[str, ...]] = {
    "poltava_city": ("poltava_raion", "poltava_rural"),
}
NEIGHBOUR_HINTS = ("околиц", "передміст")


def _with_neighbours(text: str, areas: list[str]) -> list[str]:
    """Add the districts a phrase like "та околиці" covers as well."""
    lowered = text.lower()
    if not any(hint in lowered for hint in NEIGHBOUR_HINTS):
        return areas
    grown = list(areas)
    for key in list(areas):
        for neighbour in NEIGHBOURS.get(key, ()):
            if neighbour not in grown:
                grown.append(neighbour)
    return grown


# Emoji and glued words. The Telegram preview loses its line breaks in the scrape
# integration, so "м. Полтава та околиці" and "Відбій уваги по БпЛА" arrive as
# one word. The row strips the decoration here, where the tests can hold it.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u23FF\u25A0-\u27BF"
    "\u2B00-\u2BFF\uFE0F\u200D\u20E3\u2600-\u26FF]+"
)
_GLUE = re.compile(r"(?<=[а-яіїєґ.!?])(?=[А-ЯІЇЄҐ][а-яіїєґ])")


def clean_text(text: str | None) -> str:
    """Return the message without emoji, with the glued words pulled apart."""
    if not text:
        return ""
    plain = _EMOJI.sub("", str(text))
    return " ".join(_GLUE.sub(" ", plain).split())


def find_areas(text: str) -> list[str]:
    """Return the canonical keys of the areas the message names.

    The order is the order the message names them, because the channel writes the
    districts first and the region after: "Уздовж лінії розмежування Сумської та
    Полтавської областей". A fixed table order got that backwards.
    """
    hits: list[tuple[int, str]] = []
    for key, _name, pattern in AREAS:
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            hits.append((found.start(), key))
    ordered: list[str] = []
    for _position, key in sorted(hits):
        if key not in ordered:
            ordered.append(key)
    return _with_neighbours(text, ordered)


def find_type(text: str) -> str:
    for type_name, patterns in TYPE_PATTERNS:
        if _search(patterns, text):
            return type_name
    return UNKNOWN


def classify(text: str | None) -> Marker:
    """Turn one message into a marker.

    The tests in ha-mcp/test-marker-classifier.py hold 40 real messages from
    2026-10-13 and 14, each with the verdict a person would give it.
    """
    if text is None:
        return Marker(kind=NOISE, reason="no message", text="")
    cleaned = " ".join(str(text).split())
    if cleaned in ("", "unknown", "unavailable", "none"):
        return Marker(kind=NOISE, reason="empty", text=cleaned)

    areas = find_areas(cleaned)
    threat_type = find_type(cleaned)

    # A reversal borrows a wind-down's words, so it is tested first.
    reason = _search(REVERSAL_PATTERNS, cleaned)
    if reason:
        return Marker(REVERSAL, areas, threat_type, "reversal phrase: %s" % reason, cleaned)

    reason = _search(WIND_DOWN_PATTERNS, cleaned)
    if reason:
        return Marker(WIND_DOWN, areas, threat_type, "wind-down phrase: %s" % reason, cleaned)

    reason = _search(END_PATTERNS, cleaned)
    if reason and _search(UNCERTAIN_PATTERNS, cleaned):
        # "Фіксацій не спостерігаємо. Будьте обачні — можлива поява": the
        # channel takes the all-clear back in the same breath, so the wave
        # stays open.
        return Marker(
            CONTINUATION, areas, threat_type, "end phrase, but a warned return: %s" % reason, cleaned
        )
    if reason:
        return Marker(END, areas, threat_type, "end phrase: %s" % reason, cleaned)

    # A status line that reports no contacts in the whole territory is not a new
    # alert: "Полтавська областьВся територія Без фіксацій БпЛА".
    if re.search(r"без\s+фіксацій", cleaned, re.IGNORECASE) and re.search(
        r"вся\s+територія|без\s+фіксацій", cleaned, re.IGNORECASE
    ):
        return Marker(
            CONTINUATION, areas, threat_type, "a status line: no contacts reported", cleaned
        )

    reason = _search(START_PATTERNS, cleaned)
    if reason:
        return Marker(START, areas, threat_type, "start phrase: %s" % reason, cleaned)

    reason = _search(CONTINUATION_PATTERNS, cleaned)
    if reason:
        return Marker(
            CONTINUATION, areas, threat_type, "continuation phrase: %s" % reason, cleaned
        )

    # Nothing matched. If the message does not talk about the sky at all, it is
    # an announcement; the channel's donation posts look like this.
    return Marker(NOISE, areas, threat_type, "no marker", cleaned)
