"""Normalizacja URL i tytułów do deduplikacji itemów."""

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_KEYS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "cmpid"})
_TAG_RE = re.compile(r"<[^>]+>")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_KEYS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), "")
    )


def title_hash(title: str) -> str:
    norm = " ".join(_NON_WORD_RE.sub(" ", title.lower()).split())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def strip_html(text: str) -> str:
    no_tags = _TAG_RE.sub(" ", text)
    return " ".join(html.unescape(no_tags).replace("\xa0", " ").split())
