from flask import Flask, Response, abort, url_for
import logging
import traceback
import re
import requests
import httpx
from urllib.parse import urlsplit, urlunsplit
from kan_module import KanProvider
from keshet_module import KeshetProvider
from reshet13_module import Reshet13Provider

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Initialize Providers
# ---------------------------------------------------------------------------

kan_provider = KanProvider()
keshet_provider = KeshetProvider()
reshet13_provider = Reshet13Provider()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return (
        '<h1>Israeli TV Playlist Server</h1>'
        '<ul>'
        '<li><a href="/kan_only.m3u8">/kan_only.m3u8</a> - Kan channels only</li>'
        '<li><a href="/keshet_only.m3u8">/keshet_only.m3u8</a> - Keshet channels only</li>'
        '<li><a href="/reshet13_only.m3u8">/reshet13_only.m3u8</a> - Reshet 13 channels only</li>'
        '</ul>'
    )


@app.route('/reshet13_only.m3u8')
def reshet13_only_playlist():
    """Playlist with just Reshet 13 channels"""
    # Use the provider's generate_playlist method
    playlist = reshet13_provider.generate_playlist(prefer_http=True, include_vods=False)
    
    # If you want to customize the playlist format (e.g., add both Direct and HTTP versions),
    # you can do it manually:
    channels = reshet13_provider.get_channels()
    if not channels:
        return "No Reshet 13 channels found", 404
    
    m3u = "#EXTM3U\n"
    
    for ch in channels:
        # Resolve the URL
        direct_url = reshet13_provider.resolve_url(ch.url, prefer_http=True)
        if direct_url:
            # Direct version
            m3u += (
                f'#EXTINF:-1 tvg-id="{ch.id}" tvg-logo="{ch.logo}" '
                f'group-title="Reshet 13",{ch.name} (Direct)\n'
            )
            # Add headers
            headers = reshet13_provider.get_headers(ch.id)
            if "User-Agent" in headers:
                m3u += f'#EXTVLCOPT:http-user-agent={headers["User-Agent"]}\n'
            if "Referer" in headers:
                m3u += f'#EXTVLCOPT:http-referrer={headers["Referer"]}\n'
            m3u += f'{direct_url}\n'
            
            # HTTP version (if different from direct)
            http_url = direct_url.replace("https://", "http://") if direct_url.startswith("https://") else direct_url
            if http_url != direct_url:
                m3u += (
                    f'#EXTINF:-1 tvg-id="{ch.id}" tvg-logo="{ch.logo}" '
                    f'group-title="Reshet 13",{ch.name} (HTTP)\n'
                )
                if "User-Agent" in headers:
                    m3u += f'#EXTVLCOPT:http-user-agent={headers["User-Agent"]}\n'
                if "Referer" in headers:
                    m3u += f'#EXTVLCOPT:http-referrer={headers["Referer"]}\n'
                m3u += f'{http_url}\n'
    
    return Response(m3u, mimetype='application/vnd.apple.mpegurl')


from flask import request  # ensures we get the correct host/port dynamically

TS_LINE_REGEX = re.compile(r'^(?!#)(.+\.ts)\s*$', re.MULTILINE)

def rewrite_variant_for_ts(variant_text: str) -> str:
    """
    Every .ts line (not starting with "#") is rewritten to:
        http://<host>/segments/<that-relative-path>
    to bypass ffmpeg's security restrictions.
    """
    base_url = request.host_url.rstrip('/')  # e.g. http://192.168.0.63:5000

    def _sub(match):
        ts_rel = match.group(1).strip()  # e.g. "20241022T205724/.../file.ts"
        return f"{base_url}/segments/{ts_rel}"
    
    return TS_LINE_REGEX.sub(_sub, variant_text)


@app.route('/proxy')
def proxy_variant():
    try:
        # (a) Fetch master M3U8 (with hdnea=…)
        master_url = keshet_provider.get_master_url()
        mresp = requests.get(master_url, timeout=5)
        if mresp.status_code != 200:
            return (f"Master returned {mresp.status_code}", mresp.status_code)
        master_text = mresp.text

        # (b) Pull out the first variant line (e.g. "hdntl=…/index_550.m3u8")
        variant_rel = keshet_provider.extract_first_variant(master_text)

        # (c) Reconstruct full upstream variant URL:
        split = urlsplit(master_url)
        scheme, netloc, path, query, _ = split
        base_path = path.rsplit('/', 1)[0] + '/'   # “/n12/hls/live/2103938/k12/”
        upstream_variant = urlunsplit((scheme, netloc, base_path + variant_rel, "", ""))

        # (d) Fetch that variant playlist (which lists .ts files)
        vresp = requests.get(upstream_variant, timeout=5)
        if vresp.status_code != 200:
            return (f"Variant returned {vresp.status_code}", vresp.status_code)
        variant_text = vresp.text

        # (e) Immediately rewrite every ".ts" line into "/segments/…"
        rewritten = rewrite_variant_for_ts(variant_text)

        return Response(rewritten, mimetype="application/vnd.apple.mpegurl")

    except Exception as e:
        return (f"Error in proxy_variant: {e}", 500)


@app.route('/segments/<path:ts_path>')
def proxy_segment(ts_path):
    try:
        # 1) Fetch master to get current “hdntl=…” prefix:
        master_url = keshet_provider.get_master_url()
        mresp = keshet_provider.get_master_url_with_cache(master_url = master_url)

        variant_rel = keshet_provider.extract_first_variant(mresp.text)
        
        slash_idx = variant_rel.find("/index_2200.m3u8")
        if slash_idx < 0:
            raise RuntimeError(f"Unexpected variant_rel format: {variant_rel}")
        hdntl_prefix = variant_rel[:slash_idx]
        # e.g. "hdntl=exp=1748976445~acl=%2f*~data=hdntl~hmac=…"

        # 2) Compute base path ("/n12/hls/live/2103938/k12/")
        split = urlsplit(master_url)
        scheme, netloc, path, _, _ = split
        base_path = path.rsplit('/', 1)[0] + '/'

        # 3) Build the real TS URL with that prefix:
        real_ts_url = f"{scheme}://{netloc}{base_path}{ts_path}?{hdntl_prefix}"
        logger.info(f"[proxy_segment] Fetching TS URL:\n    {real_ts_url}")

        # 4) Use Client.send(...) with stream=True (instead of get(..., stream=True)):
        client = httpx.Client(timeout=10.0, follow_redirects=True)
        req = httpx.Request("GET", real_ts_url)
        upstream_resp = client.send(req, stream=True)

        if upstream_resp.status_code != 200:
            logger.info(f"[proxy_segment] Upstream TS returned {upstream_resp.status_code}")
            return abort(upstream_resp.status_code)

        # 5) Return a streaming Response from upstream_resp.iter_bytes()
        return Response(
            upstream_resp.iter_bytes(),
            content_type="video/MP2T"
        )

    except Exception as e:
        logger.error("[proxy_segment] Caught exception:%s", e)
        traceback.print_exc()
        return abort(502)

@app.route('/keshet_only.m3u8')
def keshet_iptv_playlist():
    # This route is served for Jellyfin ffmpeg m3u8 implementation
    master_url = url_for('keshet_only_only_playlist', _external=True)
    return Response(
        "#EXTM3U\n"
        '#EXTINF:-1 tvg-id="keshet12" tvg-name="Keshet 12" group-title="Live",Keshet 12\n'
        f"{master_url}\n",
        mimetype="application/vnd.apple.mpegurl"
    )

@app.route('/keshet_iptv.m3u8')
def keshet_only_only_playlist():
    proxy_url = url_for('proxy_variant', _external=True)
    return Response(
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=1280x720\n"
        f"{proxy_url}\n",
        mimetype="application/vnd.apple.mpegurl"
    )

@app.route('/kan_only.m3u8')
def kan_only_playlist():
    """Playlist with just Kan channels"""
    # For Kan, we can use the simpler approach since URLs don't need resolution
    channels = kan_provider.get_channels()
    if not channels:
        return "No Kan channels found", 404
    
    m3u = "#EXTM3U\n"
    
    for ch in channels:
        if ch.url:
            m3u += (
                f'#EXTINF:-1 tvg-id="{ch.id}" tvg-logo="{ch.logo}" '
                f'group-title="Kan",{ch.name} (Direct)\n'
            )
            # Add headers
            headers = kan_provider.get_headers()
            if "User-Agent" in headers:
                m3u += f'#EXTVLCOPT:http-user-agent={headers["User-Agent"]}\n'
            m3u += f'{ch.url}\n'
    
    return Response(m3u, mimetype='application/vnd.apple.mpegurl')

# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # Get channel counts
    kan_count = len(kan_provider.get_channels())
    keshet_count = len(keshet_provider.get_channels())
    reshet13_count = len(reshet13_provider.get_channels())
    
    logger.info('Starting IPTV server loaded %d Kan channels, %d Keshet channels, %d Reshet 13 channels',
                kan_count, keshet_count, reshet13_count)
    
    app.run(host='0.0.0.0', port=5000, debug=True)