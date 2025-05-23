import os
import re
import json
import time
import logging
import requests
from urllib.parse import quote_plus, unquote_plus, urlparse, parse_qs

# Configure logging for the module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ---------------------------------------------------------------------------
# Constants – Kan
# ---------------------------------------------------------------------------
KAN_BASE_URL = 'https://www.kan.org.il'
KAN_BASE_KIDS_URL = 'https://www.kankids.org.il'
KAN_ARCHIVE_URL = 'https://archive.kan.org.il'
KAN_BASE_MOB_API_URL = 'https://mobapi.kan.org.il'
KAN_MOBAPI = 'https://mobapi.kan.org.il/api/mobile/subClass'

# Generic settings
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
)
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}
CACHE_TIME = 60 * 60 * 4            # 4 h – HTML / JSON cache
LINK_CACHE_TIME = 60 * 60           # 1 h – resolved stream URLs

# In‑memory caches (simple dicts – good enough for a single‑process server)
_cache: dict[str, dict] = {}
_link_cache: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Helper utilities (module‑local)
# ---------------------------------------------------------------------------

def _get_cf(url: str, timeout: int = 30) -> str:
    """Fetch *url* with basic Cloudflare‑protected site tolerance."""
    try:
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        if r.status_code != 200:
            logger.warning("%s → HTTP %s", url, r.status_code)
            return ""
        return r.text
    except Exception as exc:  # pragma: no cover – network layer
        logger.error("Kan fetch error for %s – %s", url, exc)
        return ""


def _get_cached(url: str, ttl: int = CACHE_TIME) -> str:
    now = time.time()
    hit = _cache.get(url)
    if hit and now - hit['t'] < ttl:
        return hit['body']
    body = _get_cf(url)
    if body:
        _cache[url] = {'body': body, 't': now}
    return body


def _get_json(url: str):
    try:
        r = requests.get(url, headers=DEFAULT_HEADERS)
        if r.status_code != 200:
            logger.warning("JSON %s → HTTP %s", url, r.status_code)
            return None
        return r.json().get('root') or r.json()
    except Exception as exc:
        logger.error("Kan JSON error for %s – %s", url, exc)
        return None


def _get_json_script(url: str):
    html = _get_cached(url)
    try:
        import json as _json
        m = re.search(r'type="application/json">(.*?)</script>', html)
        return _json.loads(m.group(1)) if m else None
    except Exception as exc:
        logger.debug("No inline JSON on %s – %s", url, exc)
        return None

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_url(page_url: str) -> str | None:
    """Return a playable **HLS**/embed URL extracted from a Kan page."""
    # Fast path – use link cache
    hit = _link_cache.get(page_url)
    if hit and time.time() - hit['t'] < LINK_CACHE_TIME:
        return hit['url']

    url = page_url.replace('https', 'http')
    i = url.rfind('http://')
    if i > 0:
        url = url[i:]
    url = url.replace('HLS/HLS', 'HLS')

    text = _get_cached(url)
    resolved: str | None = None

    # 1️⃣ Dailymotion embeds (kanPlayers)
    m = re.search(r'dailymotion.*?video:\s*?"(.*?)"', text, re.S)
    if m:
        resolved = f'https://www.dailymotion.com/embed/video/{m.group(1)}'

    # 2️⃣ Bynet player pages
    if not resolved and 'ByPlayer' in url:
        m = re.search(r'bynetURL:\s*"(.*?)"', text)
        if not m:
            m = re.search(r'"UrlRedirector":"(.*?)"', text)
        if m:
            resolved = m.group(1).replace('https', 'http').replace('\\u0026', '&')

    # 3️⃣ Direct HLS links already on media.kan.org.il
    if not resolved and re.search(r'media\.(ma)?kan\.org\.il', url):
        m = re.search(r'hls:\s*?"(.*?)"', text)
        if m:
            resolved = m.group(1)

    # 4️⃣ Kaltura packages
    if not resolved and 'kaltura' in url:
        km = re.search(r'window\.kalturaIframePackageData\s*=\s*\{(.*?)\};', text)
        if km:
            try:
                data = json.loads('{' + km.group(1) + '}')
                resolved = data['entryResult']['meta']['hlsStreamUrl']
            except Exception as exc:
                logger.debug("Kaltura parse error %s", exc)

    if resolved:
        _link_cache[page_url] = {'url': resolved, 't': time.time()}
    return resolved


def get_channels() -> list[dict]:
    """Return static list of Kan live channels (dicts for M3U generation)."""
    return [
        {
            "id": "kan11",
            "name": "כאן 11",
            "url": "https://kan11.media.kan.org.il/hls/live/2024514/2024514/master.m3u8",
            "logo": "https://www.kan.org.il/images/logo_kan.jpg",
            "provider": "kan",
        },
        {
            "id": "makan",
            "name": "מכאן",
            "url": "https://makan.media.kan.org.il/hls/live/2024680/2024680/master.m3u8",
            "logo": "https://www.kan.org.il/images/logo_makan.jpg",
            "provider": "kan",
        },
        {
            "id": "kan_educational",
            "name": "כאן חינוכית",
            "url": "https://kan23.media.kan.org.il/hls/live/2024691/2024691/master.m3u8",
            "logo": "https://www.kan.org.il/media/1749/23tv.jpg",
            "provider": "kan",
        },
    ]


def get_vods(max_items: int = 10) -> list[dict]:
    """Return a handful of featured VOD items scraped from Kan lobby."""
    vods: list[dict] = []
    try:
        content = _get_cached(f"{KAN_BASE_URL}/lobby/kan11")
        block_m = re.search(r'<div class="vod-section(.*?)<div class="section-content">', content, re.S)
        if not block_m:
            return vods
        item_rx = re.compile(
            r'<div aria-label="(.*?)">.*?url\((.*?)">.*?<div class="info-description">(.*?)</div>\s*<a href="(.*?)"',
            re.S,
        )
        for name, img, desc, href in item_rx.findall(block_m.group(1))[:max_items]:
            page = href if href.startswith('http') else f"{KAN_BASE_URL}{href}"
            media_url = resolve_url(page)  # eager resolve for playlist
            if not media_url:
                continue
            vods.append(
                {
                    "id": page.split('/')[-1],
                    "name": name.strip(),
                    "description": desc.strip(),
                    "url": media_url,
                    "poster": img if img.startswith('http') else f"{KAN_BASE_URL}{img}",
                    "provider": "kan",
                }
            )
    except Exception as exc:
        logger.error("Kan VOD scrape error %s", exc)
    return vods

__all__ = [
    'get_channels',
    'get_vods',
    'resolve_url',
]
