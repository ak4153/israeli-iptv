from flask import Flask, Response
import logging

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


@app.route('/keshet_only.m3u8')
def keshet_only_playlist():
    """Playlist with just the Keshet channels"""
    channels = keshet_provider.get_channels()
    if not channels:
        return "No Keshet channels found", 404
    
    m3u = "#EXTM3U\n"
    
    # Process all Keshet channels
    for ch in channels:
        # Resolve the URL
        direct_url = keshet_provider.resolve_url(ch.url, prefer_http=True)
        if direct_url:
            # Direct version
            m3u += (
                f'#EXTINF:-1 tvg-id="{ch.id}" tvg-logo="{ch.logo}" '
                f'group-title="Keshet",{ch.name} (Direct)\n'
            )
            # Add headers
            headers = keshet_provider.get_headers()
            if "User-Agent" in headers:
                m3u += f'#EXTVLCOPT:http-user-agent={headers["User-Agent"]}\n'
            m3u += f'{direct_url}\n'
            
            # HTTP version (if different from direct)
            http_url = direct_url.replace("https://", "http://") if direct_url.startswith("https://") else direct_url
            if http_url != direct_url:
                m3u += (
                    f'#EXTINF:-1 tvg-id="{ch.id}" tvg-logo="{ch.logo}" '
                    f'group-title="Keshet",{ch.name} (HTTP)\n'
                )
                if "User-Agent" in headers:
                    m3u += f'#EXTVLCOPT:http-user-agent={headers["User-Agent"]}\n'
                m3u += f'{http_url}\n'
    
    return Response(m3u, mimetype='application/vnd.apple.mpegurl')


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


# Alternative simple routes using the provider's built-in playlist generation
@app.route('/kan_simple.m3u8')
def kan_simple_playlist():
    """Simple Kan playlist using provider's generate_playlist method"""
    playlist = kan_provider.generate_playlist(prefer_http=True, include_vods=False)
    return Response(playlist, mimetype='application/vnd.apple.mpegurl')


@app.route('/keshet_simple.m3u8')
def keshet_simple_playlist():
    """Simple Keshet playlist using provider's generate_playlist method"""
    playlist = keshet_provider.generate_playlist(prefer_http=True, include_vods=False)
    return Response(playlist, mimetype='application/vnd.apple.mpegurl')


@app.route('/reshet13_simple.m3u8')
def reshet13_simple_playlist():
    """Simple Reshet13 playlist using provider's generate_playlist method"""
    playlist = reshet13_provider.generate_playlist(prefer_http=True, include_vods=False)
    return Response(playlist, mimetype='application/vnd.apple.mpegurl')


# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # Get channel counts
    kan_count = len(kan_provider.get_channels())
    keshet_count = len(keshet_provider.get_channels())
    reshet13_count = len(reshet13_provider.get_channels())
    
    logger.info('Starting IPTV server loaded %d Kan channels, %d Keshet channels, %d Reshet 13 channels',
                kan_count, keshet_count, reshet13_count)
    
    app.run(host='0.0.0.0', port=5000, debug=True)