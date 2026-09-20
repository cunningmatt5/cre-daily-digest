"""Turn Google News bounce links into real publisher URLs.

Google News RSS links are protobuf-encoded redirector pages: they don't 302,
the blob isn't base64-decodable, and the destination never appears in the
served HTML. They are also the majority of our pool, which costs us three
things — the reader lands on a Google interstitial, we can't tell what domain
a story is on, and we can't fetch the article to summarize it.

Google's own splash UI resolves them through a batchexecute RPC, using a
signature and timestamp embedded in the bounce page. Measured on live links:
14/14 resolved in ~6s at 6 workers, and 8 of those 14 then yielded usable
body text.

This endpoint is undocumented and unversioned. It can change without notice,
so every failure path here returns None and the caller keeps the original
Google link — exactly today's behaviour. ``resolve_links`` reports a success
count so a silent breakage shows up in the funnel log rather than quietly
degrading the digest.
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .feeds import HEADERS

_RPC_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_SIG_RE = re.compile(r'data-n-a-sg="([^"]+)"')
_TS_RE = re.compile(r'data-n-a-ts="([^"]+)"')
_URL_RE = re.compile(
    r'https?://(?!news\.google|www\.google|policies\.google|support\.google'
    r'|accounts\.google|lh3\.googleusercontent)[\w\-./%?=&#+:]{18,}'
)


def is_google_link(link: str) -> bool:
    return bool(link) and "news.google.com" in link


def is_direct_link(link: str) -> bool:
    """True when the URL points at a publisher page we can actually fetch.

    The single definition of this predicate. It lived in both extract.py and
    publicize.py, with ``is_google_link`` as a third, inverted copy.
    """
    return bool(link) and not is_google_link(link)


def _rpc_payload(article_id: str, timestamp: str, signature: str) -> str:
    # Shape mirrors what the Google News splash page sends for a link click.
    inner = [
        "garturlreq",
        [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None,
          None, None, None, 0, 1],
         "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
        article_id, int(timestamp), signature,
    ]
    return json.dumps([[["Fbv4je", json.dumps(inner), None, "1"]]])


def resolve_one(link: str, session=None, timeout: int = 20):
    """Return the real publisher URL for one Google News link, or None."""
    if not is_google_link(link):
        return None
    sess = session or requests.Session()
    if session is None:
        sess.headers.update(HEADERS)
    try:
        page = sess.get(link, timeout=timeout).text
        sig, ts = _SIG_RE.search(page), _TS_RE.search(page)
        if not (sig and ts):
            return None
        article_id = link.rstrip("/").split("/")[-1].split("?")[0]
        resp = sess.post(
            _RPC_URL,
            data={"f.req": _rpc_payload(article_id, ts.group(1), sig.group(1))},
            timeout=timeout,
        )
        match = _URL_RE.search(resp.text)
        return match.group(0) if match else None
    except Exception:  # noqa: BLE001 — never let this break the digest
        return None


def resolve_links(articles, max_workers: int = 6) -> dict:
    """Rewrite Google News links in place, keeping the original.

    Sets ``google_link`` to the bounce URL before overwriting ``link``. That
    field is not cosmetic: the seen-URL ledger is keyed on the link, and
    tomorrow's fetch will produce the *Google* URL again — so both must be
    retired or every resolved story would reappear as new.
    """
    targets = [a for a in articles if is_google_link(a.get("link", ""))]
    stats = {"attempted": len(targets), "resolved": 0}
    if not targets:
        return stats

    def work(article):
        session = requests.Session()
        session.headers.update(HEADERS)
        return article, resolve_one(article["link"], session)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(work, a) for a in targets]
        for future in as_completed(futures):
            try:
                article, real = future.result()
            except Exception as exc:  # noqa: BLE001
                print(f"  link resolution failed: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
                continue
            if not real:
                continue
            article["google_link"] = article["link"]
            article["link"] = real
            stats["resolved"] += 1

    if targets and stats["resolved"] == 0:
        # Total failure is the signature of Google changing the endpoint.
        # Say so loudly — the digest still works, just without direct links.
        print("WARNING: no Google News links resolved; the batchexecute endpoint "
              "may have changed. Falling back to redirect links.", file=sys.stderr)
    return stats
