#!/usr/bin/env python3
"""The marker path: no danger flag and no hold sensor are set.

This is the path the Wave Poltava integration uses. The channel's own words
decide when a wave starts and ends, so the tracker must work with `hold_on`
false for its whole life.

    python3 tests/test_markers_flow.py
"""

import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "custom_components/wave_poltava")

from markers import END, START  # noqa: E402
from tracker import WaveTracker  # noqa: E402

T0 = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
FAILS = []


def check(name, got, want):
    ok = got == want
    print("%-4s %-54s %s" % ("ok" if ok else "FAIL", name, got))
    if not ok:
        FAILS.append("%s: got %r, want %r" % (name, got, want))


def snap(tracker, at):
    return tracker.refresh(at, at.date())


def main():
    tracker = WaveTracker()
    tracker.set_release_after(30)
    # The first refresh sets the day, as the coordinator does before any post.
    snap(tracker, T0)

    tracker.note_message(
        T0,
        message="м. Полтава та околиці Увага по БпЛА",
        kind=START,
        areas=["poltava_city", "poltava_raion", "poltava_rural"],
        event_type="drone",
    )
    check("start opens the wave", snap(tracker, T0).active, True)
    check("three districts are red", len(tracker.wave.areas), 3)

    tracker.note_message(
        T0 + timedelta(minutes=10),
        message="Полтавський район — тривога по БпЛА",
        kind=START,
        areas=["poltava_raion"],
        event_type="drone",
    )
    check("a second report keeps the same wave", tracker.wave.started_at, T0)
    check("messages are counted", tracker.wave.message_count, 2)

    tracker.note_message(
        T0 + timedelta(minutes=12),
        message="м. Полтава та околиці Відбій уваги по БпЛА",
        kind=END,
        areas=["poltava_city", "poltava_raion", "poltava_rural"],
    )
    result = snap(tracker, T0 + timedelta(minutes=12))
    check("an all-clear for all three ends the wave", result.active, False)
    check("ended at the all-clear", tracker.wave.ended_at, T0 + timedelta(minutes=12))
    check("the wave keeps its start", tracker.wave.started_at, T0)
    check("the all-clear does not add a wave", tracker.waves_today, 1)
    check("the all-clear is counted", tracker.wave.message_count, 3)

    tracker.note_message(
        T0 + timedelta(minutes=20),
        message="Кременчуцький район — тривога по БпЛА",
        kind=START,
        areas=["kremenchuk_raion"],
        event_type="drone",
    )
    check("a new district opens a new wave", snap(tracker, T0 + timedelta(minutes=20)).active, True)
    check("the new wave has its own start", tracker.wave.started_at, T0 + timedelta(minutes=20))

    tracker.note_message(
        T0 + timedelta(minutes=25),
        message="Кременчуцький район Відбій",
        kind=END,
        areas=["kremenchuk_raion"],
    )
    check("the all-clear closes it", snap(tracker, T0 + timedelta(minutes=25)).active, False)

    tracker.note_message(
        T0 + timedelta(minutes=40),
        message="Лубенський район — тривога по БпЛА",
        kind=START,
        areas=["lubny_raion"],
        event_type="drone",
    )
    check("a quiet gap then a message opens a wave", snap(tracker, T0 + timedelta(minutes=40)).active, True)
    check("closed after 30 min of silence",
          snap(tracker, T0 + timedelta(minutes=71)).active, False)

    print()
    if FAILS:
        print("FAILED:", len(FAILS))
        for fail in FAILS:
            print(" -", fail)
        return 1
    print("all marker-flow checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
