# keshet_module.py
import os
import re
import json
import time
import uuid
import logging
import requests
from urllib.parse import quote_plus, unquote_plus, urlparse, parse_qs

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ---------------------------------------------------------------------------
# Constants – Keshet / Mako
# ---------------------------------------------------------------------------
MAKO_BASE_URL = 'https://www.mako.co.il'
MAKO_ENDINGS = 'platform=responsive'
MAKO_ENTITLEMENTS_SERVICES = 'https://mass.mako.co.il/ClicksStatistics/entitlementsServicesV2.jsp'

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
)
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}
CACHE_TIME = 60 * 60 * 4
LINK_CACHE_TIME = 60 * 60

MAKO_USERNAME = os.environ.get('MAKO_USERNAME', '')
MAKO_PASSWORD = os.environ.get('MAKO_PASSWORD', '')

_cache = {}
_link_cache = {}
_build_id_cache = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(url, timeout=30):
    try:
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as exc:
        logger.error("GET %s failed – %s", url, exc)
        return None


def _get_json(url):
    """Get JSON from URL with error handling"""
    r = _get(url)
    if not r:
        return None
    
    try:
        result = r.json()
        if "root" in result:
            return result["root"]
        else:
            return result
    except Exception as e:
        logger.error(f"Error parsing JSON from {url}: {str(e)}")
        return None


def _device_id():
    """Generate a device ID for Mako authentication"""
    return 'W' + str(uuid.uuid1()).replace('-', '').upper()


def _get_ticket(stream_url, cdn):
    """Get stream ticket from Mako"""
    device_id = _device_id()
    if MAKO_USERNAME:
        ticket_url = (
            f"{MAKO_ENTITLEMENTS_SERVICES}?et=gt&na=2.0&da=6gkr2ks9-4610-392g-f4s8-d743gg4623k2" \
            f"&du={device_id}&dv=&rv={cdn}&lp={stream_url}"
        )
    else:
        ticket_url = f"{MAKO_ENTITLEMENTS_SERVICES}?et=gt&lp={stream_url}&rv={cdn}"
    
    r = _get(ticket_url)
    if not r:
        return None
    
    try:
        result = r.json()
        case_id = result.get('caseId')
        
        if case_id == '1':
            return unquote_plus(result['tickets'][0]['ticket'])
        if case_id == '4' and MAKO_USERNAME:
            # Need login flow
            _mako_login(device_id)
            r2 = _get(ticket_url)
            if r2 and r2.json().get('caseId') == '1':
                return unquote_plus(r2.json()['tickets'][0]['ticket'])
        return None
    except Exception as e:
        logger.error(f"Error getting ticket: {str(e)}")
        return None


def _mako_login(device_id):
    eu = quote_plus(MAKO_USERNAME)
    dwp = quote_plus(MAKO_PASSWORD)
    login_url = (
        f"{MAKO_ENTITLEMENTS_SERVICES}?eu={eu}&da=6gkr2ks9-4610-392g-f4s8-d743gg4623k2" \
        f"&dwp={dwp}&et=ln&du={device_id}"
    )
    _get(login_url)
    # validate session
    _get(f"{MAKO_ENTITLEMENTS_SERVICES}?da=6gkr2ks9-4610-392g-f4s8-d743gg4623k2&et=gds&du={device_id}")


def _get_link(media, cdn, quality="best", prefer_http=False):
    """Extract and resolve link from media items"""
    url = ''
    for item in media:
        if item['cdn'] == cdn.upper():
            url = item['url']
            if cdn.upper() == 'AKAMAI':
                pos = url.find('?')
                if pos > 0:
                    url = url[:pos]
            break
    
    if url == '':
        logger.error(f"No URL found for CDN: {cdn}")
        return None
    
    ticket = _get_ticket(url, cdn)
    if not ticket:
        logger.error(f"Failed to get ticket for {url}")
        return None
    
    # Handle URL protocol based on preference
    if url.startswith('//'):
        url = f"{'http' if prefer_http else 'https'}:{url}"
    elif url.startswith('https://') and prefer_http:
        url = url.replace('https://', 'http://')
    
    # Construct final URL
    if '?' in url:
        final = f"{url}&{ticket}"
    else:
        final = f"{url}?{ticket}"
    
    return final

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def play_item(url, quality="best", switch_cdn=False, prefer_http=False):
    """Extract video parameters from VOD URL and play it"""
    logger.info(f"PlayItem - URL: {url}")
    
    # Generate cache key that includes format preference
    cache_key = f"{url}_{'http' if prefer_http else 'https'}"
    
    # Check cache first
    hit = _link_cache.get(cache_key)
    if hit and time.time() - hit['t'] < LINK_CACHE_TIME:
        return hit['url']
    
    # Add responsive platform param to get JSON
    params_url = f"{url}?{MAKO_ENDINGS}" if "?" not in url else f"{url}&{MAKO_ENDINGS}"
    params = _get_json(params_url)
    
    if params is None or len(params) < 1:
        logger.error(f"Failed to get params from {params_url}")
        return None
    
    try:
        video_channel_id = params["vod"]["channelId"]
        vcmid = params["vod"]["itemVcmId"]
        
        logger.debug(f"Extracted vcmid: {vcmid}, videoChannelId: {video_channel_id}")
        
        # Create params for Play function
        url_params = f"vcmid={vcmid}&videoChannelId={video_channel_id}"
        result = play(url_params, quality, switch_cdn, prefer_http)
        
        if result:
            _link_cache[cache_key] = {'url': result, 't': time.time()}
        
        return result
    except Exception as e:
        logger.error(f"Error in PlayItem: {str(e)}")
        return None


def play(url_params, quality="best", switch_cdn=False, prefer_http=False):
    """Resolve video parameters to stream URL"""
    logger.info(f"Play - URL parameters: {url_params}")
    
    try:
        # Extract vcmid and channel ID from params
        parts = parse_qs(url_params)
        vcmid = parts.get('vcmid', [''])[0]
        if not vcmid and 'vcmid=' in url_params:
            vcmid = url_params[url_params.find('vcmid=')+6: url_params.find('&videoChannelId=')]
            
        video_channel_id = parts.get('videoChannelId', [''])[0]
        if not video_channel_id and 'videoChannelId=' in url_params:
            video_channel_id = url_params[url_params.find('&videoChannelId=')+16:]
        
        if not vcmid or not video_channel_id:
            logger.error(f"Could not extract vcmid or videoChannelId from {url_params}")
            return None
        
        logger.debug(f"Extracted vcmid: {vcmid}, videoChannelId: {video_channel_id}")
        
        # Get media info
        ajax_url = (
            f"{MAKO_BASE_URL}/AjaxPage?jspName=playlist.jsp&vcmid={vcmid}" \
            f"&videoChannelId={video_channel_id}&galleryChannelId={vcmid}" \
            "&isGallery=false&consumer=web_html5&encryption=no"
        )
        
        r = _get(ajax_url)
        if not r:
            return None
            
        media_info = r.json()
        if 'media' not in media_info:
            logger.error("No media in response")
            return None
            
        media = media_info['media']
        logger.debug(f"Found {len(media)} media items")
        
        # Try different CDNs
        # Based on your logs, try AKAMAI first
        cdns = ['AKAMAI', 'AWS'] 
        
        # Try primary CDN
        link = _get_link(media, cdns[0], quality, prefer_http)
        if link is None:
            logger.debug(f"Trying backup CDN: {cdns[1]}")
            link = _get_link(media, cdns[1], quality, prefer_http)
            if link is None:
                logger.error("Failed to get link from any CDN")
                return None
                
        logger.info(f"Successfully resolved stream URL: {link}")
        return link
    except Exception as e:
        logger.error(f"Error in Play: {str(e)}")
        return None


def resolve_url(url, quality="best", prefer_http=False):
    """Main entry point to resolve a URL to a playable stream"""
    return play_item(url, quality, switch_cdn=True, prefer_http=prefer_http)


# ---------------------------------------------------------------------------
# Jellyfin-specific Functions
# ---------------------------------------------------------------------------

def get_jellyfin_stream_info(url):
    """
    Get stream info in a format suitable for Jellyfin
    """
    stream_url = resolve_url(url, prefer_http=True)
    if not stream_url:
        return None
    
    return {
        "url": stream_url,
        "headers": {
            "User-Agent": USER_AGENT
        },
        "container": "hls",
        "video_codec": "h264",
        "audio_codec": "aac"
    }


def get_required_headers():
    """
    Get the headers required for playback
    """
    return {
        "User-Agent": USER_AGENT
    }


# ---------------------------------------------------------------------------
# Static live channels + simple VOD scrape
# ---------------------------------------------------------------------------

def get_channels():
    return [
        {
            "id": "keshet12",
            "name": "קשת 12",
            "url": f"{MAKO_BASE_URL}/mako-vod-live-tv/VOD-6540b8dcb64fd31006.htm",
            "logo": "https://img.mako.co.il/2017/06/21/keshet_2017_logo_a.jpg",
            "provider": "keshet",
        },
        {
            "id": "traitors",
            "name": "traitors",
            "url": "https://www.mako.co.il/mako-vod-keshet/the_traitors-s1/VOD-c901dc765866691027.htm",
            "logo": "https://img.mako.co.il/2017/06/21/keshet_2017_logo_a.jpg",
            "provider": "keshet",
        },
    ]


def get_vods(max_items=10):
    vods = []
    try:
        # For simplicity, we'll just return an empty list
        # VOD scraping can be implemented later if needed
        pass
    except Exception as exc:
        logger.error("Mako VOD scrape error – %s", exc)
    return vods


# ---------------------------------------------------------------------------
# M3U8 Playlist Generation
# ---------------------------------------------------------------------------

def resolve_channel_to_m3u8(channel_url, channel_name="", channel_id="", logo="", prefer_http=True):
    """
    Resolves a channel URL to an M3U8 playlist entry
    """
    stream_url = resolve_url(channel_url, prefer_http=prefer_http)
    if not stream_url:
        logger.error(f"Failed to resolve {channel_url}")
        return ""
    
    # Build the M3U8 entry
    tvg_id = f' tvg-id="{channel_id}"' if channel_id else ""
    tvg_name = f' tvg-name="{channel_name}"' if channel_name else ""
    tvg_logo = f' tvg-logo="{logo}"' if logo else ""
    
    # For Jellyfin compatibility, add user-agent header
    entry = f'#EXTINF:-1{tvg_id}{tvg_name}{tvg_logo},{channel_name or "Keshet Channel"}\n'
    entry += f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n'
    entry += f'{stream_url}\n'
    
    return entry


def generate_m3u8_playlist(prefer_http=True):
    """
    Generates a complete M3U8 playlist with all available channels
    """
    channels = get_channels()
    playlist = "#EXTM3U\n"
    
    for channel in channels:
        entry = resolve_channel_to_m3u8(
            channel["url"], 
            channel["name"], 
            channel["id"], 
            channel.get("logo", ""),
            prefer_http=prefer_http
        )
        if entry:
            playlist += entry
    
    return playlist


def resolve_custom_url_to_m3u8(url, name="", prefer_http=True):
    """
    Resolves a custom URL to an M3U8 playlist entry
    """
    return resolve_channel_to_m3u8(url, name, prefer_http=prefer_http)


# ---------------------------------------------------------------------------
# Flask Server Extension Functions
# ---------------------------------------------------------------------------

def get_stream_response(url, prefer_http=True):
    """
    Helper function to use in Flask routes that returns appropriate 
    response format for stream URL requests
    """
    stream_url = resolve_url(url, prefer_http=prefer_http)
    if not stream_url:
        return {
            "error": f"Failed to resolve URL: {url}",
            "success": False
        }, 404
    
    return {
        "original_url": url,
        "resolved_url": stream_url,
        "headers": {
            "User-Agent": USER_AGENT
        },
        "success": True
    }


def get_redirect_response(url, prefer_http=True):
    """
    Helper function for Flask routes that redirects to the resolved stream
    """
    stream_url = resolve_url(url, prefer_http=prefer_http)
    if not stream_url:
        return {
            "error": f"Failed to resolve URL: {url}",
            "success": False
        }, 404
    
    return stream_url


__all__ = [
    'get_channels', 
    'get_vods', 
    'resolve_url', 
    'play_item',
    'play',
    'generate_m3u8_playlist', 
    'resolve_channel_to_m3u8', 
    'resolve_custom_url_to_m3u8',
    'get_stream_response',
    'get_redirect_response',
    'get_jellyfin_stream_info',
    'get_required_headers'
]


# If run directly, test resolving the Keshet 12 channel
if __name__ == "__main__":
    # Test resolving Keshet 12 channel
    test_url = f"https://www.mako.co.il/mako-vod-keshet/the_traitors-s1/VOD-c901dc765866691027.htm"
    
    # Try HTTP version first (preferred for TV compatibility)
    result = resolve_url(test_url, prefer_http=True)
    
    if result:
        print(f"\nSuccessfully resolved URL!")
        print(f"Stream URL: {result}")
        
        # Generate M3U8 entry
        m3u8_entry = resolve_custom_url_to_m3u8(test_url, "Keshet 12", prefer_http=True)
        print(f"\nM3U8 Entry:\n{m3u8_entry}")
        
        # Show Jellyfin required headers
        print(f"\nRequired Headers for Jellyfin:")
        headers = get_required_headers()
        for key, value in headers.items():
            print(f"  {key}: {value}")
    else:
        print(f"\nFailed to resolve URL: {test_url}")
        
    # Also show how this would be used in a Flask server
    print("\nFlask Server Example Response:")
    response = get_stream_response(test_url)
    if isinstance(response, tuple):
        print(f"Error: {response[0]}")
    else:
        print(f"Success: {response}")