from flask import Flask, Response, jsonify, request, redirect
import logging
from urllib.parse import quote_plus, unquote_plus, urlparse, parse_qs

import kan_module as kan
import keshet_module as keshet
import reshet13_module as reshet13

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
# https://claude.ai/chat/be5a0de7-4639-4fbf-9cdf-be3467ad1e3e
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _playlist() -> str:
    """Generate M3U8 playlist on the fly using channel / VOD data from modules."""
    host = request.host
    m3u = "#EXTM3U\n"

    # Live channels
    for ch in kan.get_channels():
        m3u += (
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
            f'group-title="Kan",{ch["name"]}\n{ch["url"]}\n'
        )
    for ch in keshet.get_channels():
        proxied = f"http://{host}/resolve/keshet?url={quote_plus(ch['url'])}"
        m3u += (
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
            f'group-title="Keshet",{ch["name"]}\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{proxied}\n'
        )
    # Add Reshet 13 channels
    for ch in reshet13.get_channels():
        proxied = f"http://{host}/resolve/reshet13?url={quote_plus(ch['url'])}"
        m3u += (
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
            f'group-title="Reshet 13",{ch["name"]}\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{proxied}\n'
        )

    # VOD
    for v in kan.get_vods():
        m3u += (
            f'#EXTINF:-1 tvg-id="kan-vod-{v["id"]}" tvg-logo="{v.get("poster", "")}" '
            f'group-title="Kan VOD",{v["name"]}\n{v["url"]}\n'
        )
    for v in keshet.get_vods():
        proxied = f"http://{host}/resolve/keshet?url={quote_plus(v['url'])}"
        m3u += (
            f'#EXTINF:-1 tvg-id="keshet-vod-{v["id"]}" tvg-logo="{v.get("poster", "")}" '
            f'group-title="Keshet VOD",{v["name"]}\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{proxied}\n'
        )
    # Add Reshet 13 VODs
    for v in reshet13.get_vods():
        proxied = f"http://{host}/resolve/reshet13?url={quote_plus(v['url'])}"
        m3u += (
            f'#EXTINF:-1 tvg-id="reshet13-vod-{v["id"]}" tvg-logo="{v.get("poster", "")}" '
            f'group-title="Reshet 13 VOD",{v["name"]}\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{proxied}\n'
        )
    return m3u


def _tv_playlist() -> str:
    """Generate M3U8 playlist optimized for TV devices."""
    host = request.host
    m3u = "#EXTM3U\n"

    # Live channels
    for ch in kan.get_channels():
        m3u += (
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
            f'group-title="Kan",{ch["name"]}\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{ch["url"]}\n'
        )
    for ch in keshet.get_channels():
        proxied = f"http://{host}/resolve/keshet?url={quote_plus(ch['url'])}&mode=tv"
        m3u += (
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
            f'group-title="Keshet",{ch["name"]}\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{proxied}\n'
        )
    # Add Reshet 13 channels with TV mode
    for ch in reshet13.get_channels():
        proxied = f"http://{host}/resolve/reshet13?url={quote_plus(ch['url'])}&mode=tv"
        m3u += (
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
            f'group-title="Reshet 13",{ch["name"]}\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{proxied}\n'
        )

    # VOD - simplified for TV
    for v in keshet.get_vods():
        proxied = f"http://{host}/resolve/keshet?url={quote_plus(v['url'])}&mode=tv"
        m3u += (
            f'#EXTINF:-1 tvg-id="keshet-vod-{v["id"]}" tvg-logo="{v.get("poster", "")}" '
            f'group-title="Keshet VOD",{v["name"]}\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{proxied}\n'
        )
    # Add Reshet 13 VODs with TV mode
    for v in reshet13.get_vods():
        proxied = f"http://{host}/resolve/reshet13?url={quote_plus(v['url'])}&mode=tv"
        m3u += (
            f'#EXTINF:-1 tvg-id="reshet13-vod-{v["id"]}" tvg-logo="{v.get("poster", "")}" '
            f'group-title="Reshet 13 VOD",{v["name"]}\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{proxied}\n'
        )
    return m3u



def _tv_proxy_playlist() -> str:
    """Generate M3U8 playlist with all streams proxied for TV compatibility"""
    host = request.host
    m3u = "#EXTM3U\n"

    # Live channels
    for ch in kan.get_channels():
        proxied = f"http://{host}/proxy?url={quote_plus(ch['url'])}"
        m3u += (
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
            f'group-title="Kan",{ch["name"]}\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{proxied}\n'
        )
    for ch in keshet.get_channels():
        proxied = f"http://{host}/resolve/keshet?url={quote_plus(ch['url'])}&proxy=true"
        m3u += (
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
            f'group-title="Keshet",{ch["name"]}\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{proxied}\n'
        )
    # Add Reshet 13 channels with proxy mode
    for ch in reshet13.get_channels():
        proxied = f"http://{host}/resolve/reshet13?url={quote_plus(ch['url'])}&proxy=true"
        m3u += (
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
            f'group-title="Reshet 13",{ch["name"]}\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{proxied}\n'
        )

    return m3u


def _proxy_stream(url, original_headers=None):
    """
    Stream proxy function - fetches content with headers and streams it back
    """
    import requests
    from flask import Response, stream_with_context
    
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.mako.co.il/",
    }
    if original_headers:
        headers.update(original_headers)
    
    try:
        # First check the content type
        head_req = requests.head(url, headers=headers, timeout=5)
        content_type = head_req.headers.get('Content-Type', '')
        
        # If it's an M3U8 playlist, we need to modify it to proxy the segments too
        if 'm3u8' in content_type.lower() or url.endswith('.m3u8'):
            # Get the playlist content
            playlist_req = requests.get(url, headers=headers, timeout=10)
            playlist_content = playlist_req.text
            
            # Extract the base URL for relative paths
            base_url = url.rsplit('/', 1)[0] + '/'
            
            # Replace segment URLs with proxied URLs
            modified_lines = []
            for line in playlist_content.splitlines():
                if line.startswith('#'):
                    # Keep comment/directive lines as is
                    modified_lines.append(line)
                elif line.strip():
                    # It's a segment URL - make it absolute and then proxy it
                    if not line.startswith('http'):
                        # It's a relative URL, make it absolute
                        segment_url = base_url + line
                    else:
                        segment_url = line
                    
                    # Replace with a proxied URL
                    proxied_segment = f"/proxy?url={quote_plus(segment_url)}"
                    modified_lines.append(proxied_segment)
                else:
                    # Keep empty lines
                    modified_lines.append(line)
            
            # Return the modified playlist
            modified_playlist = '\n'.join(modified_lines)
            return Response(modified_playlist, mimetype='application/vnd.apple.mpegurl')
        
        # For other content types, just proxy as-is
        req = requests.get(url, headers=headers, stream=True)
        
        response_headers = {}
        for header in ['Content-Type', 'Content-Length']:
            if header in req.headers:
                response_headers[header] = req.headers[header]
        
        return Response(
            stream_with_context(req.iter_content(chunk_size=8192)),
            status=req.status_code,
            headers=response_headers
        )
        
    except Exception as e:
        logger.error(f"Proxy error: {str(e)}")
        return jsonify({'error': f'Proxy error: {str(e)}'}), 500

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return (
        '<h1>Israeli TV Playlist Server</h1>'
        '<ul>'
        '<li><a href="/playlist.m3u8">/playlist.m3u8</a> - Standard playlist</li>'
        '<li><a href="/tv.m3u8">/tv.m3u8</a> - TV optimized playlist</li>'
        '<li><a href="/tv_proxy.m3u8">/tv_proxy.m3u8</a> - TV playlist with proxied streams</li>'
        '<li><a href="/kan_only.m3u8">/kan_only.m3u8</a> - Kan channels only</li>'
        '<li><a href="/keshet_only.m3u8">/keshet_only.m3u8</a> - Keshet channels only</li>'
        '<li><a href="/reshet13_only.m3u8">/reshet13_only.m3u8</a> - Reshet 13 channels only</li>'
        '<li><a href="/channels">/channels</a> - List all channels</li>'
        '<li><a href="/vods">/vods</a> - List all VODs</li>'
        '<li><a href="/proxy">/proxy</a> - Proxy a stream (add ?url=...)</li>'
        '</ul>'
    )


@app.route('/playlist.m3u8')
def playlist():
    return Response(_playlist(), mimetype='application/vnd.apple.mpegurl')


@app.route('/tv.m3u8')
def tv_playlist():
    """TV-optimized playlist with HTTP URLs and headers"""
    return Response(_tv_playlist(), mimetype='application/vnd.apple.mpegurl')


@app.route('/tv_proxy.m3u8')
def tv_proxy_playlist():
    """TV-optimized playlist with all streams proxied"""
    return Response(_tv_proxy_playlist(), mimetype='application/vnd.apple.mpegurl')

@app.route('/resolve/reshet13')
def resolve_reshet13():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    
    # Check if the request is coming from a TV
    user_agent = request.headers.get('User-Agent', '').lower()
    is_tv = 'tv' in user_agent or 'webos' in user_agent or 'lg' in user_agent
    
    # Allow forcing proxy mode with a parameter
    force_proxy = request.args.get('proxy', 'false').lower() == 'true'
    
    # TV mode forces HTTP protocol
    mode = request.args.get('mode', '')
    prefer_http = True if mode == 'tv' else True  # Default to HTTP for better compatibility
    
    # Format parameter for raw URL
    format_param = request.args.get('format', '')
    
    # Get the resolved URL
    resolved = reshet13.resolve_url(url, prefer_http=prefer_http)
    
    if not resolved:
        return jsonify({'error': 'Failed to resolve URL'}), 404
    
    # Handle different response formats
    if format_param == 'raw':
        return Response(resolved, mimetype='text/plain')
    elif format_param == 'json':
        # Extract channel_id from URL
        channel_id = url.replace("reshet13://", "") if url.startswith("reshet13://") else ""
        headers = reshet13.get_channel_headers(channel_id)
        
        return jsonify({
            'original_url': url,
            'resolved_url': resolved,
            'headers': headers
        })
    
    # For TVs or when proxy is forced, proxy the stream
    if is_tv or force_proxy:
        # Extract channel_id from URL
        channel_id = url.replace("reshet13://", "") if url.startswith("reshet13://") else ""
        # Get headers for this channel
        headers = reshet13.get_channel_headers(channel_id)
        # Proxy the stream through server
        return _proxy_stream(resolved, headers)
    else:
        # For other devices, just redirect
        return redirect(resolved)

@app.route('/reshet13_only.m3u8')
def reshet13_only_playlist():
    """Playlist with just Reshet 13 channels, using different approaches"""
    host = request.host
    channels = reshet13.get_channels()
    if not channels:
        return "No Reshet 13 channels found", 404
        
    m3u = "#EXTM3U\n"
    
    # Add all channels with different streaming methods
    for ch in channels:
        # 1. Direct URL
        direct_url = reshet13.resolve_url(ch["url"], prefer_http=True)
        if direct_url:
            m3u += (
                f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
                f'group-title="Reshet 13",{ch["name"]} (Direct)\n'
                f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
                f'{direct_url}\n'
            )
        
        # # 2. Proxy version
        # proxied = f"http://{host}/resolve/reshet13?url={quote_plus(ch['url'])}&proxy=true"
        # m3u += (
        #     f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
        #     f'group-title="Reshet 13",{ch["name"]} (Proxied)\n'
        #     f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
        #     f'{proxied}\n'
        # )
        
        # 3. HTTP version
        http_url = direct_url.replace("https://", "http://") if direct_url and direct_url.startswith("https://") else direct_url
        if http_url:
            m3u += (
                f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
                f'group-title="Reshet 13",{ch["name"]} (HTTP)\n'
                f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
                f'{http_url}\n'
            )
    
    return Response(m3u, mimetype='application/vnd.apple.mpegurl')

@app.route('/keshet_only.m3u8')
def keshet_only_playlist():
    """Playlist with just the Keshet channel, using different approaches"""
    host = request.host
    keshet_channels = keshet.get_channels()
    if not keshet_channels:
        return "No Keshet channels found", 404
        
    ch = keshet_channels[0]
    m3u = "#EXTM3U\n"
    
    # 1. Direct URL (standard)
    direct_url = keshet.resolve_url(ch["url"], prefer_http=True)
    if direct_url:
        m3u += (
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
            f'group-title="Keshet",{ch["name"]} (Direct)\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{direct_url}\n'
        )
    
    # 2. Proxy version
    # proxied = f"http://{host}/resolve/keshet?url={quote_plus(ch['url'])}&proxy=true"
    # m3u += (
    #     f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
    #     f'group-title="Keshet",{ch["name"]} (Proxied)\n'
    #     f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
    #     f'{proxied}\n'
    # )
    
    # 3. HTTP version
    http_url = direct_url.replace("https://", "http://") if direct_url else ""
    if http_url:
        m3u += (
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
            f'group-title="Keshet",{ch["name"]} (HTTP)\n'
            f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
            f'{http_url}\n'
        )
    
    return Response(m3u, mimetype='application/vnd.apple.mpegurl')

@app.route('/kan_only.m3u8')
def kan_only_playlist():
    """Playlist with just Kan channels, using different approaches"""
    host = request.host
    kan_channels = kan.get_channels()
    if not kan_channels:
        return "No Kan channels found", 404
        
    m3u = "#EXTM3U\n"
    
    # Add all channels with different streaming methods
    for ch in kan_channels:
        # 1. Direct URL
        direct_url = ch["url"]
        if direct_url:
            m3u += (
                f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
                f'group-title="Kan",{ch["name"]} (Direct)\n'
                f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
                f'{direct_url}\n'
            )
        
        # # 2. HTTP version
        # http_url = direct_url.replace("https://", "http://") if direct_url and direct_url.startswith("https://") else direct_url
        # if http_url and http_url != direct_url:
        #     m3u += (
        #         f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
        #         f'group-title="Kan",{ch["name"]} (HTTP)\n'
        #         f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
        #         f'{http_url}\n'
        #     )
        
        # # 3. Proxied version for maximum compatibility
        # proxied = f"http://{host}/proxy?url={quote_plus(direct_url)}"
        # m3u += (
        #     f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-logo="{ch["logo"]}" '
        #     f'group-title="Kan",{ch["name"]} (Proxied)\n'
        #     f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
        #     f'{proxied}\n'
        # )
    
    return Response(m3u, mimetype='application/vnd.apple.mpegurl')

@app.route('/channels')
def channels():
    return jsonify({
        'kan': kan.get_channels(),
        'keshet': keshet.get_channels(),
        'reshet13': reshet13.get_channels(),
    })

# Update the vods route
@app.route('/vods')
def vods():
    return jsonify({
        'kan': kan.get_vods(),
        'keshet': keshet.get_vods(),
        'reshet13': reshet13.get_vods(),
    })


@app.route('/resolve/kan')
def resolve_kan():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    resolved = kan.resolve_url(url)
    return redirect(resolved) if resolved else (jsonify({'error': 'fail'}), 404)


@app.route('/resolve/keshet')
def resolve_keshet():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    
    # Check if the request is coming from a TV (you can detect this using the User-Agent)
    user_agent = request.headers.get('User-Agent', '').lower()
    is_tv = 'tv' in user_agent or 'webos' in user_agent or 'lg' in user_agent
    
    # Also allow forcing proxy mode with a parameter
    force_proxy = request.args.get('proxy', 'false').lower() == 'true'
    
    # Get mode parameter - tv mode forces HTTP protocol
    mode = request.args.get('mode', '')
    prefer_http = True if mode == 'tv' else True  # Default to HTTP for better compatibility
    
    # Get format parameter - if raw, return the URL as text
    format_param = request.args.get('format', '')
    
    # Get the resolved URL
    resolved = keshet.resolve_url(url, prefer_http=prefer_http)
    
    if not resolved:
        return jsonify({'error': 'Failed to resolve URL'}), 404
    
    # Handle different response formats
    if format_param == 'raw':
        return Response(resolved, mimetype='text/plain')
    elif format_param == 'json':
        return jsonify({
            'original_url': url,
            'resolved_url': resolved,
            'headers': {'User-Agent': USER_AGENT}
        })
    
    # For TVs (or when proxy is forced), proxy the stream instead of redirecting
    if is_tv or force_proxy:
        # This will proxy the stream through your server
        return _proxy_stream(resolved)
    else:
        # For other devices, just redirect
        return redirect(resolved)


@app.route('/proxy')
def proxy():
    """
    Proxy a stream URL, adding necessary headers
    """
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'Missing url parameter'}), 400
    
    return _proxy_stream(url)


@app.route('/check')
def check_url():
    """
    Check if a URL is directly accessible or if it needs to be proxied
    """
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'Missing url parameter'}), 400
    
    try:
        import requests
        headers = {'User-Agent': USER_AGENT}
        r = requests.head(url, headers=headers, timeout=5)
        
        return jsonify({
            'url': url,
            'status_code': r.status_code,
            'accessible': r.status_code == 200,
            'content_type': r.headers.get('Content-Type', '')
        })
    except Exception as e:
        return jsonify({
            'url': url,
            'error': str(e),
            'accessible': False
        })

# ---------------------------------------------------------------------------

if __name__ == '__main__':
    logger.info('Starting IPTV server loaded %d Kan channels, %d Keshet channels',
                len(kan.get_channels()), len(keshet.get_channels()))
    app.run(host='0.0.0.0', port=5000, debug=True)