#!/usr/bin/env python3
"""Offline tests for the district set in wave_layer/tracker.py.

    python3 tests/test_districts.py

WHY
    The channel marks the start and the end of an alert, and it does so per
    district. It clears one district while another is still under alert:

        06:55  Полтавський район  Відбій тривоги по БпЛА
        07:06  Кременчуцький район  Відбій тривоги по БпЛА

    A wave that ends on the first "Відбій" is 63 minutes long; a wave that ends
    when the last district clears is 150 minutes. The second is what a person
    lived through, so the tracker keeps a set of districts.

WHAT IS TESTED
    a wave opens on a start marker, even with the hold off
    a partial all-clear does not close the wave
    the last all-clear closes it
    a wind-down and a reversal do not close it
    a start while a wave is open extends it, it does not open a second one
    an all-clear for a district that never declared does nothing
    a first start after the wave closed opens a new wave
    the district set survives a restart
"""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "custom_components/wave_poltava")
from tracker import WaveTracker  # noqa: E402

T0 = datetime(2026, 10, 14, 6, 36, tzinfo=timezone.utc)
FAILS = []


def check(name, got, want):
    ok = got == want
    print("%-4s %-56s %s" % ("ok" if ok else "FAIL", name, got))
    if not ok:
        FAILS.append("%s: got %r, want %r" % (name, got, want))


def tracker():
    t = WaveTracker()
    t.set_release_after(30)
    return t


def marker(t, at, kind, areas, message="", type_name=None):
    """One message from the channel, with its marker."""
    return t.note_message(
        at, message=message, kind=kind, areas=areas, event_type=type_name
    )


def snap(t, at):
    return t.refresh(at, at.date())


print("== 1. a start marker opens a wave, and the hold is off ==")
t = tracker()
started = marker(t, T0, "start", ["poltava_raion", "myrhorod_raion"],
                 "🔴Полтавський район Миргородський район Ракетна небезпека", "rocket")
check("start reports a new wave", started, True)
s = snap(t, T0 + timedelta(seconds=5))
check("the wave is active", s.active, True)
check("its districts", t.areas, ["poltava_raion", "myrhorod_raion"])
check("it is red although the hold is off", s.reason.startswith("the wave is active"), True)

print("== 2. a continuation does not close the wave, and adds no district ==")
marker(t, T0 + timedelta(minutes=5), "continuation", ["kremenchuk_raion"],
       "❗️2 мКР. Курсують в сторону Роменського району")
s = snap(t, T0 + timedelta(minutes=5, seconds=5))
check("still active", s.active, True)
# A continuation names districts for many reasons: "В сторону Чутівського
# району." is a route, not a declaration. Only a start puts a district under
# alert, or the set grows with districts that no all-clear ever removes.
check("a continuation adds no district",
      sorted(t.areas), ["myrhorod_raion", "poltava_raion"])
check("the continuation is counted", t.wave.message_count, 2)

print("== 3. a wind-down does not close the wave ==")
marker(t, T0 + timedelta(minutes=10), "wind_down", [],
       "🟢Якщо нічого не зміниться, очікуємо на відбій ракетної небезпеки.")
s = snap(t, T0 + timedelta(minutes=10, seconds=5))
check("still active after a wind-down", s.active, True)

print("== 4. a reversal does not close the wave either ==")
marker(t, T0 + timedelta(minutes=12), "reversal", ["poltava_raion"],
       "Полтавський район — відбою поки не очікуємо. Є нові фіксації.")
s = snap(t, T0 + timedelta(minutes=12, seconds=5))
check("still active after a reversal", s.active, True)

print("== 5. a partial all-clear does not close the wave ==")
# The start declared two districts; a third arrives later by declaration.
marker(t, T0 + timedelta(minutes=15), "start", ["kremenchuk_raion"],
       "🟡Кременчуцький район — тривога по БпЛА", "drone")
marker(t, T0 + timedelta(minutes=17), "end", ["poltava_raion"],
       "Полтавський район Відбій ракетної небезпеки")
s = snap(t, T0 + timedelta(minutes=17, seconds=5))
check("still active", s.active, True)
check("one district left", sorted(t.areas), ["kremenchuk_raion", "myrhorod_raion"])
check("the declaration is what added it", "kremenchuk_raion" in t.areas, True)
check("the cleared district is remembered", "poltava_raion" in t.cleared, True)

print("== 6. the last all-clear closes the wave ==")
marker(t, T0 + timedelta(minutes=20), "end", ["kremenchuk_raion", "myrhorod_raion"],
       "Миргородський район Кременчуцький район Відбій ракетної небезпеки")
s = snap(t, T0 + timedelta(minutes=20, seconds=5))
check("the wave is closed", s.active, False)
check("no district left", t.areas, [])
check("ended at the last all-clear", s.wave.ended_at, T0 + timedelta(minutes=20))
check("reason", s.reason, "every district is clear")

print("== 7. an all-clear with no open wave does nothing ==")
t2 = tracker()
marker(t2, T0, "end", ["poltava_raion"], "Полтавський район Відбій тривоги по БпЛА")
s = snap(t2, T0 + timedelta(seconds=5))
check("no wave was opened", s.active, False)
check("no wave at all", t2.wave.started, False)

print("== 8. a start after a close opens a new wave ==")
marker(t, T0 + timedelta(hours=2), "start", ["kremenchuk_raion"],
       "🟡Кременчуцький район — тривога по БпЛА", "drone")
s = snap(t, T0 + timedelta(hours=2, seconds=5))
check("a new wave is active", s.active, True)
check("its district", t.areas, ["kremenchuk_raion"])
check("the cleared set is empty again", t.cleared, [])

print("== 9. the district set survives a restart ==")
saved = t.save()
t3 = tracker()
restored = t3.restore(saved, T0 + timedelta(hours=2, minutes=1))
check("restored", restored, True)
check("the districts came back", t3.areas, ["kremenchuk_raion"])
s = snap(t3, T0 + timedelta(hours=2, minutes=2))
check("and the wave is still active", s.active, True)

print("== 10. a silent channel closes a wave even with districts named ==")
t4 = tracker()
marker(t4, T0, "start", ["poltava_raion"], "🔴Ракетна небезпека", "rocket")
s = snap(t4, T0 + timedelta(minutes=31))
check("closed after the silence", s.active, False)
check("the end is the silence deadline", t4.wave.ended_at, T0 + timedelta(minutes=30))
check("the length includes the silence", t4.duration_minutes(T0 + timedelta(minutes=31)), 30.0)
check("the reason names the silence", "went quiet" in s.reason, True)
check("the district set is emptied", t4.areas, [])
check("the district moved to cleared", t4.cleared, ["poltava_raion"])

print("")
if FAILS:
    print("FAILURES: %d" % len(FAILS))
    for line in FAILS:
        print("  - %s" % line)
    sys.exit(1)
print("all checks passed")
