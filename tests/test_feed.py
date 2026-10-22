#!/usr/bin/env python3
"""Test the Telegram preview parser against a saved page.

    python3 tests/test_feed.py

The page is a real slice of https://telegram.me/s/monitoringplt, saved on
2026-10-22. It holds three posts, one of them multi-line, so the test holds the
two things that matter: the line breaks survive, and the HTML entities are
decoded.
"""

import sys
from pathlib import Path

sys.path.insert(0, "custom_components/wave_poltava")

from feed import parse_page  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "monitoring.html"
FAILS = []


def check(name, got, want):
    ok = got == want
    print("%-4s %-56s %s" % ("ok" if ok else "FAIL", name, got))
    if not ok:
        FAILS.append("%s: got %r, want %r" % (name, got, want))


def main():
    posts = parse_page(FIXTURE.read_text())
    check("post count", len(posts), 3)
    check("ids are ascending", [p.post_id for p in posts], [58909, 58910, 58911])
    check("newest text", posts[-1].text,
          "⚠️Загроза застосування балістичного озброєння з Брянської області")
    check("newest time", posts[-1].at.isoformat(),
          "2026-10-22T10:05:47+00:00")

    page = """
    <div class="tgme_widget_message js-widget_message" data-post="ch/7">
      <div class="tgme_widget_message_text js-message_text">м. Полтава та околиці<br/>
      Відбій уваги по БпЛА<br/>Заходи безпеки&#33;</div>
      <time datetime="2026-10-22T11:00:00+00:00">11:00</time>
    </div>
    <div class="tgme_widget_message js-widget_message" data-post="ch/8">
      <div class="tgme_widget_message_photo"></div>
    </div>
    """
    one = parse_page(page)
    check("photo post skipped", len(one), 1)
    check("line breaks kept", one[0].text,
          "м. Полтава та околиці\nВідбій уваги по БпЛА\nЗаходи безпеки!")
    check("tags removed", "<div" in one[0].text, False)

    print()
    if FAILS:
        print("FAILED:", len(FAILS))
        for fail in FAILS:
            print(" -", fail)
        return 1
    print("all feed checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
