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

# ---------------------------------------------------------------------------
# Initialize Logging Sysyem and Logger
# ---------------------------------------------------------------------------
# Logging system and Logger initialization.
# Logger will log informations as,
# Example: Sat Jun 14 21:55:14 2025 - Israeli-IPTV - Info - User Logged in successfully

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Initialize Providers
# ---------------------------------------------------------------------------
# Providers initialization.
# 1. Kan Provider from Kan module.
# 2. Keshet Provider from Keshet module.
# 3. Reshet Provider for Reshet13 module.

kan_provider = KanProvider()
keshet_provider = KeshetProvider()
reshet13_provider = Reshet13Provider()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
# The application uses these routes,
# 1. Root ("/")
# 2. Reshet13 only ("/reshet13_only.m3u8")
# 3. Keshet only ("/keshet_only.m3u8")
# 4. Kan only ("/kan_only.m3u8")
# 5. Keshet IPTV ("/keshet_iptv.m3u8")
# 6. Proxy ("/proxy")
# 7. TS segments ("/segments/<path:ts_path>")

# Defines Root 
@app.route('/')
def index():
    """
    Returns the main index of the application.
    """
    return (
        '<h1>Israeli TV Playlist Server</h1>'
        '<ul>'
        '<li><a href="/kan_only.m3u8">/kan_only.m3u8</a> - Kan channels only</li>'
        '<li><a href="/keshet_only.m3u8">/keshet_only.m3u8</a> - Keshet channels only</li>'
        '<li><a href="/reshet13_only.m3u8">/reshet13_only.m3u8</a> - Reshet 13 channels only</li>'
        '</ul>'
    )


# Defines Reshet13-Only
@app.route('/reshet13_only.m3u8')
def reshet13_only_playlist() -> Response:
    """
    Generates a Reshet13-only M3U8 playlist channel.
    
    This Flask route dynamically generates a M3U8 playlist by fetching
    channels from 'reshet13_provider'. It handles URL resolution
    (preferring HTTP protocol) and embeds necessary HTTP headers
    (User-Agent, Referer) into the playlist.
    
    The playlist customisation includes generating both Direct and HTTP
    versions of the channel URLs if they differ.

    Returns:
        If channel found:
            A Flask `Response` object containing the generated M3U8 playlist
            with `application/vnd.apple.mpegurl` mimetype.
        
        If no channel found: 
            Returns a string message "No Reshet 13 channels found" with a
            404 Not Found status.
    
    Notes:
        - The generation prioritizes HTTP URLs by setting `prefer_http=True`.
        - VOD (Video On Demand) content is explicitly excluded (`include_vods=False`).
        - Headers are retrieved per channel ID from `reshet13_provider`.

    Edge Cases:
        - Handles scenarios where the HTTP version of a channel URL differs
          from its direct URL, providing both in the playlist for compatibility.
    """
    
    # Generates via Provider's generate_playlist method
    playlist = reshet13_provider.generate_playlist(prefer_http=True, include_vods=False)
    
    # Playlist Customisation (e.g. HTTP or Direct versions)
    channels = reshet13_provider.get_channels()
    if not channels:
        return "No Reshet 13 channels found", 404
    
    m3u = "#EXTM3U\n"
    
    # Resolve URLs
    for ch in channels:
        direct_url = reshet13_provider.resolve_url(ch.url, prefer_http=True)
        if direct_url:
            # Direct version
            m3u += (
                f'#EXTINF:-1 tvg-id="{ch.id}" tvg-logo="{ch.logo}" '
                f'group-title="Reshet 13",{ch.name} (Direct)\n'
            )
            
            # Add headers
            headers = reshet13_provider.get_headers(ch.id) # Headers are from channel
            if "User-Agent" in headers:
                m3u += f'#EXTVLCOPT:http-user-agent={headers["User-Agent"]}\n'
            if "Referer" in headers:
                m3u += f'#EXTVLCOPT:http-referrer={headers["Referer"]}\n'
            m3u += f'{direct_url}\n'
            
            # Edge Case:
            # HTTP version (if different from direct)
            http_url = direct_url.replace("https://", "http://") if direct_url.startswith("https://") else direct_url
            if http_url != direct_url:
                m3u += (
                    f'#EXTINF:-1 tvg-id="{ch.id}" tvg-logo="{ch.logo}" '
                    f'group-title="Reshet 13",{ch.name} (HTTP)\n'
                )
                
                # Add Headers
                if "User-Agent" in headers:
                    m3u += f'#EXTVLCOPT:http-user-agent={headers["User-Agent"]}\n'
                if "Referer" in headers:
                    m3u += f'#EXTVLCOPT:http-referrer={headers["Referer"]}\n'
                m3u += f'{http_url}\n'
    
    return Response(m3u, mimetype='application/vnd.apple.mpegurl')


from flask import request  # ensures that we get the correct host/port dynamically

# Compiles a regular expression to match and capture .ts file URLs.
# It specifically targets lines that do not start with '#' (comments).
TS_LINE_REGEX = re.compile(r'^(?!#)(.+\.ts)\s*$', re.MULTILINE)

def rewrite_variant_for_ts(variant_text: str) -> str:
    """
    Rewrites .ts file paths in HLS variant playlists.

    Every .ts line (not starting with "#") is rewritten to include the
    full base URL, changing its format to:
    "http://<host>/segments/<that-relative-path>"

    This ensures that FFmpeg's security restrictions are bypassed by
    providing absolute URLs for the transport stream segments.
    
    Args:
        variant_text (str): The content of the HLS variant playlist
                            containing relative .ts file paths.

    Returns:
        str: The rewritten HLS variant playlist with absolute .ts URLs.
    """
    
    base_url = request.host_url.rstrip('/')  # Example: http://192.168.0.63:5000

    def _sub(match):
        ts_rel = match.group(1).strip()  # Example: "20241022T205724/.../file.ts"
        return f"{base_url}/segments/{ts_rel}"
    
    return TS_LINE_REGEX.sub(_sub, variant_text)

# Defines Proxy
@app.route('/proxy')
def proxy_variant() -> Response:
    """
    Proxies an HLS master playlist from Keshet 12, extracts the first variant,
    and rewrites its .ts segment URLs for direct access.

    This function fetches the master M3U8 playlist from the Keshet provider,
    identifies the primary variant playlist, and then modifies the URLs of
    the individual .ts video segments within that variant. This rewriting
    bypasses security restrictions (e.g., FFmpeg's) that might prevent direct
    playback of relative or insecure segment URLs.

    Returns:
        A Flask Response object containing the rewritten M3U8 variant playlist
        with the appropriate mimetype.
        Returns an error message string and an HTTP status code (4xx or 500)
        if any step in the proxy process fails.
    """
    
    try:
        # (a) Fetch the master M3U8 playlist from the Keshet provider.
        # This playlist contains references to various video quality variants.
        master_url = keshet_provider.get_master_url()
        mresp = requests.get(master_url, timeout=5)
        
        # Check if the master playlist fetch was successful.
        if mresp.status_code != 200:
            return (f"Master returned {mresp.status_code}", mresp.status_code)
        master_text = mresp.text
        
        # (b) Extract the relative path of the first (presumably highest quality)
        # variant playlist from the master M3U8 content.
        variant_rel = keshet_provider.extract_first_variant(master_text)

        # (c) Reconstruct the full absolute URL for the upstream variant playlist.
        # This involves parsing the master URL and combining its scheme, network location,
        # and base path with the extracted relative variant path.
        split = urlsplit(master_url)
        scheme, netloc, path, query, _ = split
        # Determine the base path of the master URL (e.g., directory where master.m3u8 is located).
        base_path = path.rsplit('/', 1)[0] + '/'
        # Combine components to form the complete URL for the variant playlist.
        upstream_variant = urlunsplit((scheme, netloc, base_path + variant_rel, "", ""))

        # (d) Fetch the actual variant playlist, which lists the individual .ts segment files.
        vresp = requests.get(upstream_variant, timeout=5)

        # Check if the variant playlist fetch was successful.
        if vresp.status_code != 200:
            return (f"Variant returned {vresp.status_code}", vresp.status_code)
        variant_text = vresp.text

        # (e) Rewrite every ".ts" line in the variant playlist.
        # This function converts relative .ts URLs into absolute ones, typically
        # pointing to a local /segments/ endpoint to bypass external security checks.
        rewritten = rewrite_variant_for_ts(variant_text)

        # Return the modified variant playlist with the appropriate M3U8 mimetype.
        return Response(rewritten, mimetype="application/vnd.apple.mpegurl")
        
    except Exception as e:
        # Catch any unexpected errors during the process and return a 500 Internal Server Error.
        return (f"Error in proxy_variant: {e}", 500)


# Defines TS segments 
@app.route('/segments/<path:ts_path>')
def proxy_segment(ts_path) -> Response:
    """
    Proxies an individual HLS .ts video segment.

    This function is responsible for fetching and streaming a specific
    `.ts` video segment to the client. It dynamically determines the
    necessary authentication prefix (e.g., `hdntl`) by first fetching
    the master playlist, constructs the full upstream URL for the segment,
    and then streams the segment's bytes directly to the client.

    Args:
        ts_path (str): The relative path of the .ts segment requested
                       (e.g., '20241022T205724/.../file.ts').
    
    Returns:
        A Flask `Response` object streaming the .ts video data with
        `video/MP2T` content type.
        Aborts with an HTTP status code (4xx or 5xx) if the segment
        cannot be fetched or if an unexpected error occurs.
    """
    
    try:
        try:
        # a) Fetch the master M3U8 playlist to dynamically obtain the
        #    current authentication/access prefix (e.g., `hdntl=...`).
        #    This prefix is typically short-lived and required for segment access.
        master_url = keshet_provider.get_master_url()
        # Use a cached version of the master URL fetch to reduce redundant requests.
        mresp = keshet_provider.get_master_url_with_cache(master_url=master_url)

        # Extract the first variant's relative path from the master playlist.
        # This variant path contains the necessary `hdntl` prefix.
        variant_rel = keshet_provider.extract_first_variant(mresp.text)

        # Locate the position of "/index_2200.m3u8" within the variant_rel string.
        # This helps isolate the `hdntl` prefix which comes before it.        
        slash_idx = variant_rel.find("/index_2200.m3u8")
        if slash_idx < 0:
            # If the expected pattern is not found, raise an error as the prefix
            # cannot be reliably extracted.
            raise RuntimeError(f"Unexpected variant_rel format: {variant_rel}")
        # Extract the authentication prefix (e.g., "hdntl=exp=...hmac=...")
        # from the beginning of the variant_rel string up to the found index.
        hdntl_prefix = variant_rel[:slash_idx]
        
        # 2) Compute the base path for the .ts segments.
        # This path is derived from the master playlist's URL, representing
        # the directory where the HLS segments are typically located.
        split = urlsplit(master_url)
        scheme, netloc, path, _, _ = split
        # Extract the directory path (e.g., "/n12/hls/live/2103938/k12/")
        base_path = path.rsplit('/', 1)[0] + '/'

        # 3) Build the complete, real URL for the .ts segment.
        # This URL combines the scheme, network location, base path, the
        # requested `ts_path`, and the dynamically obtained `hdntl_prefix`.
        real_ts_url = f"{scheme}://{netloc}{base_path}{ts_path}?{hdntl_prefix}"
        logger.info(f"[proxy_segment] Fetching TS URL:\n    {real_ts_url}")
        
        # 4) Use `httpx.Client` to send a GET request for the .ts segment.
        # `httpx` is preferred for its modern async capabilities and robust streaming.
        # `stream=True` is crucial here: it allows streaming the response content
        # directly without loading the entire segment into memory, which is efficient
        # for large video files. `follow_redirects=True` ensures redirects are handled.
        client = httpx.Client(timeout=10.0, follow_redirects=True)
        req = httpx.Request("GET", real_ts_url)
        upstream_resp = client.send(req, stream=True)

        # Check if the upstream segment fetch was successful.
        if upstream_resp.status_code != 200:
            logger.info(f"[proxy_segment] Upstream TS returned {upstream_resp.status_code}")
            # If not successful, abort the request with the upstream status code.
            return abort(upstream_resp.status_code)
            
        # 5) Return a streaming Flask `Response`.
        # `upstream_resp.iter_bytes()` provides an iterator that yields bytes
        # from the upstream response as they are received. This ensures
        # efficient, real-time streaming of the video segment to the client
        # without buffering the entire file.
        # The `content_type` is set to `video/MP2T` for MPEG Transport Stream.
        return Response(
            upstream_resp.iter_bytes(),
            content_type="video/MP2T"
        )

    except Exception as e:
        # Catch any unexpected exceptions that occur during the proxy process.
        logger.error("[proxy_segment] Caught exception: %s", e)
        # Print the full traceback for debugging purposes.
        traceback.print_exc()
        # Abort the request with a 502 Bad Gateway error, indicating a server-side issue.
        return abort(502)

# Defines Keshet-Only
@app.route('/keshet_only.m3u8')
def keshet_iptv_playlist() -> Response:
    """
    Generates a Keshet-only M3U8 playlist channel for IPTV clients.

    This Flask route acts as a simple wrapper to present the
    `/reshet13_only.m3u8` endpoint (which contains the actual Keshet 12
    playlist logic) in a format suitable for IPTV players like Jellyfin's
    FFmpeg integration. It effectively creates a single-channel M3U8
    playlist pointing to the dynamically generated Keshet 12 stream.

    Returns:
        A Flask `Response` object containing a short M3U8 playlist that
        redirects to the main Keshet 12 playlist endpoint. The mimetype
        is set to `application/vnd.apple.mpegurl`.
    """

    # This route is specifically designed to be served for IPTV clients
    # that require a direct M3U8 file with simple channel entries,
    # such as Jellyfin's FFmpeg M3U8 implementation.
    
    # Generate the absolute URL for the `reshet13_only_playlist` route.
    # This URL will be embedded in the M3U8 as the actual stream source.
    master_url = url_for('reshet13_only_playlist', _external=True)
    
    # Construct the M3U8 playlist content.
    # It includes the standard M3U header, channel information (EXTINF),
    # and the absolute URL to the dynamically generated Keshet 12 playlist.
    return Response(
        "#EXTM3U\n"
        '#EXTINF:-1 tvg-id="keshet12" tvg-name="Keshet 12" tvg-logo="/logos/keshet12.png" group-title="Live",Keshet 12\n'
        f"{master_url}\n",
        mimetype="application/vnd.apple.mpegurl"
    )

# Defines Keshet IPTV
@app.route('/keshet_iptv.m3u8')
def keshet_only_only_playlist() -> Response:
    """
    Generates a minimalist M3U8 playlist redirecting to the proxy variant.

    This Flask route creates a very basic HLS playlist (`.m3u8` file)
    designed to point directly to the `/proxy` endpoint. It's intended
    to serve as an intermediate playlist, allowing clients to fetch
    the actual, processed HLS variant stream via the proxy.
    This structure helps in serving the stream without exposing the
    complexities of the upstream source or its security mechanisms directly
    to the client.

    Returns:
        A Flask `Response` object containing a simple M3U8 playlist with
        a single stream entry, directing to the `proxy_variant` route.
        The mimetype is `application/vnd.apple.mpegurl`.
    """
    # Generate the absolute URL for the `proxy_variant` route.
    # This URL will be the only stream entry in this minimalist playlist.
    proxy_url = url_for('proxy_variant', _external=True)

    # Construct the M3U8 playlist content.
    # #EXTM3U: Standard HLS playlist header.
    # #EXT-X-VERSION:3: Specifies HLS protocol version 3.
    # #EXT-X-STREAM-INF: Provides information about the stream, including
    #                    estimated BANDWIDTH and RESOLUTION for the client's
    #                    selection. Note: These are placeholder values as the
    #                    actual variant details are handled by the proxy.
    # {proxy_url}: The actual URL to the HLS stream, handled by the `/proxy` route.
    return Response(
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=1280x720\n" # Placeholder info for the stream
        f"{proxy_url}\n",
        mimetype="application/vnd.apple.mpegurl"
    )

# Defines Kan-Only
@app.route('/kan_only.m3u8')
def kan_only_playlist() -> Response:
    """Generates an M3U8 playlist containing only Kan (Israeli Public Broadcasting Corporation) channels.

    This function retrieves a list of available Kan channels from `kan_provider`.
    Unlike other providers, Kan URLs typically do not require complex resolution
    or HTTP/HTTPS preference handling. It constructs an M3U8 playlist with
    direct URLs for each channel and embeds necessary headers for playback.

    Returns:
        A Flask `Response` object containing the generated M3U8 playlist
        with `application/vnd.apple.mpegurl` mimetype.
        Returns a string message "No Kan channels found" with a 404 Not Found
        status if the `kan_provider` returns no channels.
    """

    # Retrieve all available Kan channels from the dedicated provider.
    # For Kan, a simpler approach is used as their URLs are generally direct
    # and do not require complex resolution logic like other providers.
    channels = kan_provider.get_channels()

    # If no channels are returned by the provider, send a 404 Not Found error.
    if not channels:
        return "No Kan channels found", 404

    # Initialize the M3U8 playlist string with the standard header.
    m3u = "#EXTM3U\n"

    # Iterate through each retrieved Kan channel to add its entry to the playlist.
    for ch in channels:
        # Only add channels that have a valid URL.
        if ch.url:
            # Add the EXTINF tag with channel metadata (ID, logo, group, name).
            # The "(Direct)" suffix indicates it's the direct URL, given Kan's simpler nature.
            m3u += (
                f'#EXTINF:-1 tvg-id="{ch.id}" tvg-logo="{ch.logo}" '
                f'group-title="Kan",{ch.name} (Direct)\n'
            )

            # Retrieve any necessary HTTP headers for playback from the Kan provider.
            headers = kan_provider.get_headers()
            # If a User-Agent header is provided, embed it as an EXTVLCOPT tag
            # for players that support VLC-specific options (like VLC media player).
            if "User-Agent" in headers:
                m3u += f'#EXTVLCOPT:http-user-agent={headers["User-Agent"]}\n'
            # Append the direct channel URL to the playlist.
            m3u += f'{ch.url}\n'

    # Return the fully generated M3U8 playlist as a Flask Response object,
    # setting the appropriate mimetype for HLS playlists.
    return Response(m3u, mimetype='application/vnd.apple.mpegurl')
    
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # Get channel counts
    kan_count = len(kan_provider.get_channels())
    keshet_count = len(keshet_provider.get_channels())
    reshet13_count = len(reshet13_provider.get_channels())
    
    # Logs the information 
    logger.info('Starting IPTV server loaded %d Kan channels, %d Keshet channels, %d Reshet 13 channels',
                kan_count, keshet_count, reshet13_count)
    
    # Sets host, port and debug
    app.run(host='0.0.0.0', port=5000, debug=True)
