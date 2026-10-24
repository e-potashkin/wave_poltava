#!/usr/bin/env python3
"""Offline tests for wave_layer/tracker.py. No Home Assistant needed.

    python3 ha-mcp/test-wave-tracker.py
"""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "custom_components/wave_poltava")
from tracker import WaveTracker  # noqa: E402

T0 = datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)
FAILS = []


def check(name, got, want):
    ok = got == want
    print("%-4s %-58s %s" % ("ok" if ok else "FAIL", name, got))
    if not ok:
        FAILS.append("%s: got %r, want %r" % (name, got, want))


def tracker():
    t = WaveTracker()
    t.set_release_after(30)
    return t


def snap(t, at):
    return t.refresh(at, at.date())


print("== 1. one message opens a wave ==")
t = tracker()
t.note_message(T0, message="м. Полтава — БпЛА", area="Полтава", danger="БпЛА",
               source="sensor.monitoring_poltavshchina", event_type="drone")
t.set_flag("danger_on", True)
t.set_flag("hold_on", True)
s = snap(t, T0 + timedelta(seconds=5))
check("state active", s.active, True)
check("message_count", s.wave.message_count, 1)
check("started_at", s.wave.started_at, T0)
check("duration while running", t.duration_minutes(T0 + timedelta(minutes=10)), 10.0)

print("== 2. a second message inside the timeout extends the wave ==")
t.note_message(T0 + timedelta(minutes=25), message="Проліт БпЛА", area="Полтава",
               danger="БпЛА")
s = snap(t, T0 + timedelta(minutes=25, seconds=5))
check("still active", s.active, True)
check("message_count", s.wave.message_count, 2)
check("started_at unchanged", s.wave.started_at, T0)
check("deadline moved", t.deadline, T0 + timedelta(minutes=55))

print("== 3. a silent hold does not end the wave before the timeout ==")
t.set_flag("hold_on", False)
t.set_flag("danger_on", False)
s = snap(t, T0 + timedelta(minutes=40))
check("active after hold off", s.active, True)
check("reason", s.reason, "inside the release delay after the last message")

print("== 4. the wave ends at last message + timeout ==")
s = snap(t, T0 + timedelta(minutes=56))
check("idle", s.active, False)
check("ended_at", s.wave.ended_at, T0 + timedelta(minutes=55))
check("duration", t.duration_minutes(T0 + timedelta(minutes=56)), 55.0)
check("reason", s.reason, "release delay passed after the last message")

print("== 5. the next message opens a new wave ==")
t.note_message(T0 + timedelta(hours=3), message="нова хвиля", area="Полтавська область")
s = snap(t, T0 + timedelta(hours=3, minutes=1))
check("active again", s.active, True)
check("new started_at", s.wave.started_at, T0 + timedelta(hours=3))
check("count reset", s.wave.message_count, 1)
check("old end cleared", s.wave.ended_at, None)

print("== 6. a restart inside the timeout resumes nothing, only displays ==")
saved = t.wave.as_dict()
t2 = tracker()
check("restore accepted", t2.restore(saved, T0 + timedelta(hours=3, minutes=10)), True)
s2 = snap(t2, T0 + timedelta(hours=3, minutes=10))
check("resumed active", s2.active, True)
check("restored flag", s2.restored, True)
check("message_count kept", s2.wave.message_count, 1)
s3 = snap(t2, T0 + timedelta(hours=3, minutes=31))
check("ends at the real deadline", s3.wave.ended_at, T0 + timedelta(hours=3, minutes=30))

print("== 7. a restart after the timeout does not resurrect the alert ==")
t3 = tracker()
saved = t.wave.as_dict()
check("restore accepted", t3.restore(saved, T0 + timedelta(hours=5)), True)
s4 = snap(t3, T0 + timedelta(hours=5))
check("idle", s4.active, False)
check("ended_at is the real end", s4.wave.ended_at, T0 + timedelta(hours=3, minutes=30))

print("== 8. a stale saved wave is dropped ==")
t4 = tracker()
saved = dict(t.wave.as_dict())
saved["last_message_at"] = (T0 - timedelta(hours=30)).isoformat()
saved["started_at"] = (T0 - timedelta(hours=30)).isoformat()
check("restore refused", t4.restore(saved, T0), False)
s5 = snap(t4, T0)
check("idle", s5.active, False)
check("no wave", s5.wave.started, False)

print("== 9. day counters reset on a new day ==")
t5 = tracker()
t5.day_key = T0.date()  # a first message lands on a known day
t5.note_message(T0, message="a")
snap(t5, T0)
check("waves today", t5.waves_today, 1)
t5.note_message(T0 + timedelta(minutes=2), message="b")
t5.refresh(T0 + timedelta(minutes=3), T0.date())
check("second message, same wave", t5.waves_today, 1)
check("two messages", t5.messages_today, 2)
t5.note_message(T0 + timedelta(hours=4), message="c")
t5.refresh(T0 + timedelta(hours=4), T0.date())
check("new wave same day", t5.waves_today, 2)
check("old wave closed early", t5.wave.started_at, T0 + timedelta(hours=4))
s6 = t5.refresh(T0 + timedelta(days=1), (T0 + timedelta(days=1)).date())
check("waves reset", s6.waves_today, 0)
check("messages reset", s6.messages_today, 0)

print("== 10. bad timeout input is ignored ==")
t6 = tracker()
t6.set_release_after("unknown")
check("kept default", t6.release_after_minutes, 30)
t6.set_release_after(45)
check("accepted 45", t6.release_after_minutes, 45)
t6.set_release_after(0)
check("rejected 0", t6.release_after_minutes, 45)

print("== 10b. a completed wave survives a restart ==")
# A finished wave is display-only, so it cannot resurrect an alert. Its whole
# record is what the dashboard showed, and a restart must keep it. The old
# restore refused it because Wave.started was False once ended_at was set, and
# the next save then wrote an empty wave over the stored one.
ended = {
    "started_at": (T0 + timedelta(hours=6)).isoformat(),
    "last_message_at": (T0 + timedelta(hours=6, minutes=4)).isoformat(),
    "ended_at": (T0 + timedelta(hours=6, minutes=42)).isoformat(),
    "message_count": 4,
    "last_message": "м. Полтава та околиці Відбій тривоги по БпЛА",
    "last_area": "м. Полтава",
    "last_danger": "drone",
    "last_source": "https://telegram.me/s/monitoringplt",
    "last_event_type": "drone",
    "areas": [],
    "cleared": ["poltava_city"],
    "last_kind": "end",
}
t7 = tracker()
check("completed wave restored", t7.restore(ended, T0 + timedelta(days=3)), True)
s7 = snap(t7, T0 + timedelta(days=3))
check("it is not active", s7.active, False)
check("start kept", t7.wave.started_at, T0 + timedelta(hours=6))
check("end kept", t7.wave.ended_at, T0 + timedelta(hours=6, minutes=42))
check("length kept", t7.duration_minutes(T0 + timedelta(days=3)), 42.0)
check("message count kept", t7.wave.message_count, 4)
check("last message kept", t7.wave.last_message,
      "м. Полтава та околиці Відбій тривоги по БпЛА")
check("the reason names the ended wave", s7.reason, "every district is clear")
check("restored flag shown once", s7.restored, True)

print("")
if FAILS:
    print("FAILURES: %d" % len(FAILS))
    for f in FAILS:
        print("  - %s" % f)
    sys.exit(1)
print("all checks passed")

print("== 11. a hold that is already off does not extend the wave ==")
# Measured 2026-10-14: the channel posted "no targets are recorded", the parser
# cleared its danger flag at 12:46, the hold expired at 12:47, and the wave
# stayed red until 13:10 — because the deadline was `last message + 30 minutes`.
# The wave must end with the hold instead.
t = tracker()
t.note_message(T0, message="❗️Швидкісних цілей в напрямку Полтавської області", area="Полтавської області",
               danger="Швидкісних цілей", source="sensor.monitoring_poltavshchina", event_type="ballistic")
t.set_flag("danger_on", True, T0)
t.set_flag("hold_on", True, T0)
s = snap(t, T0 + timedelta(minutes=1))
check("wave is red while the hold is on", s.active, True)

t.set_flag("danger_on", False, T0 + timedelta(minutes=6))
t.set_flag("hold_on", False, T0 + timedelta(minutes=7))
s = snap(t, T0 + timedelta(minutes=7, seconds=5))
check("wave ends with the hold, not 30 minutes later", s.active, False)
check("ended at the moment the hold released", s.wave.ended_at, T0 + timedelta(minutes=7))
check("reason names the hold", s.reason, "the hold released, so the wave ended with it")

print("== 12. a new wave still starts after that ==")
t.note_message(T0 + timedelta(hours=2), message="м. Полтава — БпЛА", area="Полтава",
               danger="БпЛА", source="sensor.monitoring_poltavshchina", event_type="drone")
s = snap(t, T0 + timedelta(hours=2, seconds=5))
check("a later message opens a new wave", s.active, True)
check("the old end is kept", t.wave.started_at, T0 + timedelta(hours=2))

print("== 13. a hold that never released keeps the fallback deadline ==")
t = tracker()
t.note_message(T0, message="м. Полтава — БпЛА", area="Полтава", danger="БпЛА",
               source="sensor.monitoring_poltavshchina", event_type="drone")
s = snap(t, T0 + timedelta(minutes=29))
check("still inside the release delay", s.active, True)
s = snap(t, T0 + timedelta(minutes=31))
check("the fallback deadline still closes it", s.active, False)
check("ended at last message + delay", s.wave.ended_at, T0 + timedelta(minutes=30))
