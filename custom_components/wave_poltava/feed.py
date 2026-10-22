"""Read the public Telegram preview of the Poltava monitoring channel.

The preview page holds the last twenty-odd posts as static HTML. This module
turns it into posts with an id, the text the channel wrote, and the post time.

    page HTML
      |
      v
    parse_page()  ->  [Post(id, text, at), ...]  oldest first
      |
      v
    coordinator   ->  one call per post the channel publishes

The page separates the lines of a post with <br/>, and a plain text extraction
loses them. The line is the unit the channel writes in, so <br/> becomes a line
break here and is not flattened to a space.

The page escapes punctuation as HTML entities ("Заходи безпеки&#33;"), so the
text is unescaped after the tags are stripped.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_LOGGER = logging.getLogger(__name__)

_POST = re.compile(r'data-post="[^"/]+/(\d+)"')
_TEXT = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    re.DOTALL,
)
_TIME = re.compile(r'<time[^>]*\bdatetime="([^"]+)"')
_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"[ \t\u00a0]+")


@dataclass(frozen=True, slots=True)
class Post:
    """One message from the channel."""

    post_id: int
    text: str
    at: datetime | None


def _extract_text(chunk: str) -> str:
    """Return the post text, with <br/> kept as a line break."""
    found = _TEXT.search(chunk)
    if found is None:
        return ""
    body = _BREAK.sub("\n", found.group(1))
    body = _TAG.sub("", body)
    body = html.unescape(body)
    lines: list[str] = []
    for line in body.splitlines():
        line = _SPACE.sub(" ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _extract_time(chunk: str) -> datetime | None:
    """Return the post time in UTC, when the page carries one."""
    found = _TIME.search(chunk)
    if found is None:
        return None
    try:
        moment = datetime.fromisoformat(found.group(1))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def parse_page(page: str) -> list[Post]:
    """Turn the preview HTML into posts, oldest first.

    A post is a `<div ... data-post="channel/N">` wrapper. The text and the time
    live inside the wrapper, so the page is split at the wrappers and each
    chunk is read on its own. A post with no text (a photo or a sticker) is
    skipped, and a duplicate id keeps the last copy.
    """
    matches = list(_POST.finditer(page))
    found: dict[int, Post] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page)
        chunk = page[match.end() : end]
        text = _extract_text(chunk)
        if not text:
            continue
        post = Post(int(match.group(1)), text, _extract_time(chunk))
        found[post.post_id] = post
    return [found[key] for key in sorted(found)]


async def async_fetch(
    session: Any,
    url: str,
    timeout: int = 20,
) -> list[Post]:
    """Fetch the preview page and parse it."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    import aiohttp  # noqa: PLC0415

    async with session.get(
        url,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=timeout),
    ) as response:
        response.raise_for_status()
        page = await response.text()
    posts = parse_page(page)
    if not posts:
        raise ValueError("the preview page carries no posts")
    return posts
