# keshet_module.py
import os
import re
import requests
import uuid
import logging
import requests
from urllib.parse import quote_plus, unquote_plus, parse_qs
from typing import List, Optional, Dict, Any

from base_provider import BaseProvider, Channel, VOD

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

MAKO_USERNAME = os.environ.get('MAKO_USERNAME', '')
MAKO_PASSWORD = os.environ.get('MAKO_PASSWORD', '')


class KeshetProvider(BaseProvider):
    """Keshet (Mako) TV provider implementation."""
    
    def __init__(self):
        super().__init__("keshet")
        self.base_url = MAKO_BASE_URL
        self.endings = MAKO_ENDINGS
        self.entitlements_services = MAKO_ENTITLEMENTS_SERVICES
        self.username = MAKO_USERNAME
        self.password = MAKO_PASSWORD
        
        # Additional caches specific to Keshet
        self._build_id_cache: Dict[str, Any] = {}
    
    # ---------------------------------------------------------------------------
    # Helper utilities (private methods)
    # ---------------------------------------------------------------------------
    
    def get_master_url(self) -> str:
        """
        Get the master URL for the main Keshet channel.
        This is used to resolve the main channel stream URL.
        """
        return self.resolve_url(
            self.get_channels()[0].url,
            prefer_http=True
        )
    
    def get_master_url_with_cache(self, ttl: int = 720) -> Optional[str]:
        """
        Get the master URL for the main Keshet channel with caching.
        Makes a GET request only if the TTL has passed.
        """
        cache_key = "master_url"
        
        cached_url = self._get_from_cache(cache_key, ttl)
        if cached_url:
            self.logger.debug("Using cached master URL")
            return cached_url

        master_url = self.get_master_url()
        mresp = requests.get(master_url, timeout=5)
        if mresp.status_code != 200:
            self.logger.error(f"Failed to fetch master URL: {master_url}")
            return None

        self._set_cache(cache_key, mresp)
        return mresp

    @staticmethod
    def extract_first_variant(master_text: str) -> str:
        m = re.search(r'^(?!#)(.*index_2200\.m3u8)\s*$', master_text, re.MULTILINE)
        if not m:
            raise ValueError("No variant .m3u8 line found in master playlist.")
        return m.group(1).strip()

    def _get(self, url: str, timeout: int = 30) -> Optional[requests.Response]:
        """Fetch URL with error handling."""
        try:
            headers = self.get_headers()
            r = requests.get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as exc:
            self.logger.error("GET %s failed – %s", url, exc)
            return None
    
    def _get_json(self, url: str) -> Optional[Dict]:
        """Get JSON from URL with error handling."""
        r = self._get(url)
        if not r:
            return None
        
        try:
            result = r.json()
            if "root" in result:
                return result["root"]
            else:
                return result
        except Exception as e:
            self.logger.error(f"Error parsing JSON from {url}: {str(e)}")
            return None
    
    def _device_id(self) -> str:
        """Generate a device ID for Mako authentication."""
        return 'W' + str(uuid.uuid1()).replace('-', '').upper()
    
    def _get_ticket(self, stream_url: str, cdn: str) -> Optional[str]:
        """Get stream ticket from Mako."""
        device_id = self._device_id()
        if self.username:
            ticket_url = (
                f"{self.entitlements_services}?et=gt&na=2.0&da=6gkr2ks9-4610-392g-f4s8-d743gg4623k2" \
                f"&du={device_id}&dv=&rv={cdn}&lp={stream_url}"
            )
        else:
            ticket_url = f"{self.entitlements_services}?et=gt&lp={stream_url}&rv={cdn}"
        
        r = self._get(ticket_url)
        if not r:
            return None
        
        try:
            result = r.json()
            case_id = result.get('caseId')
            
            if case_id == '1':
                return unquote_plus(result['tickets'][0]['ticket'])
            if case_id == '4' and self.username:
                # Need login flow
                self._mako_login(device_id)
                r2 = self._get(ticket_url)
                if r2 and r2.json().get('caseId') == '1':
                    return unquote_plus(r2.json()['tickets'][0]['ticket'])
            return None
        except Exception as e:
            self.logger.error(f"Error getting ticket: {str(e)}")
            return None
    
    def _mako_login(self, device_id: str):
        """Login to Mako."""
        eu = quote_plus(self.username)
        dwp = quote_plus(self.password)
        login_url = (
            f"{self.entitlements_services}?eu={eu}&da=6gkr2ks9-4610-392g-f4s8-d743gg4623k2" \
            f"&dwp={dwp}&et=ln&du={device_id}"
        )
        self._get(login_url)
        # validate session
        self._get(f"{self.entitlements_services}?da=6gkr2ks9-4610-392g-f4s8-d743gg4623k2&et=gds&du={device_id}")
    
    def _get_link(self, media: List[Dict], cdn: str, quality: str = "best", prefer_http: bool = False) -> Optional[str]:
        """Extract and resolve link from media items."""
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
            self.logger.error(f"No URL found for CDN: {cdn}")
            return None
        
        ticket = self._get_ticket(url, cdn)
        if not ticket:
            self.logger.error(f"Failed to get ticket for {url}")
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
    
    def _play_item(self, url: str, quality: str = "best", switch_cdn: bool = False, prefer_http: bool = False) -> Optional[str]:
        """Extract video parameters from VOD URL and play it."""
        self.logger.info(f"PlayItem - URL: {url}")
        
        # Generate cache key that includes format preference
        cache_key = f"{url}_{'http' if prefer_http else 'https'}"
        
        # Check link cache first
        cached_url = self._get_from_link_cache(cache_key)
        if cached_url:
            return cached_url
        
        # Add responsive platform param to get JSON
        params_url = f"{url}?{self.endings}" if "?" not in url else f"{url}&{self.endings}"
        params = self._get_json(params_url)
        
        if params is None or len(params) < 1:
            self.logger.error(f"Failed to get params from {params_url}")
            return None
        
        try:
            video_channel_id = params["vod"]["channelId"]
            vcmid = params["vod"]["itemVcmId"]
            
            self.logger.debug(f"Extracted vcmid: {vcmid}, videoChannelId: {video_channel_id}")
            
            # Create params for Play function
            url_params = f"vcmid={vcmid}&videoChannelId={video_channel_id}"
            result = self._play(url_params, quality, switch_cdn, prefer_http)
            
            if result:
                self._set_link_cache(cache_key, result)
            
            return result
        except Exception as e:
            self.logger.error(f"Error in PlayItem: {str(e)}")
            return None
    
    def _play(self, url_params: str, quality: str = "best", switch_cdn: bool = False, prefer_http: bool = False) -> Optional[str]:
        """Resolve video parameters to stream URL."""
        self.logger.info(f"Play - URL parameters: {url_params}")
        
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
                self.logger.error(f"Could not extract vcmid or videoChannelId from {url_params}")
                return None
            
            self.logger.debug(f"Extracted vcmid: {vcmid}, videoChannelId: {video_channel_id}")
            
            # Get media info
            ajax_url = (
                f"{self.base_url}/AjaxPage?jspName=playlist.jsp&vcmid={vcmid}" \
                f"&videoChannelId={video_channel_id}&galleryChannelId={vcmid}" \
                "&isGallery=false&consumer=web_html5&encryption=no"
            )
            
            r = self._get(ajax_url)
            if not r:
                return None
                
            media_info = r.json()
            if 'media' not in media_info:
                self.logger.error("No media in response")
                return None
                
            media = media_info['media']
            self.logger.debug(f"Found {len(media)} media items")
            
            # Try different CDNs
            cdns = ['AKAMAI', 'AWS'] 
            
            # Try primary CDN
            link = self._get_link(media, cdns[0], quality, prefer_http)
            if link is None:
                self.logger.debug(f"Trying backup CDN: {cdns[1]}")
                link = self._get_link(media, cdns[1], quality, prefer_http)
                if link is None:
                    self.logger.error("Failed to get link from any CDN")
                    return None
                    
            self.logger.info(f"Successfully resolved stream URL: {link}")
            return link
        except Exception as e:
            self.logger.error(f"Error in Play: {str(e)}")
            return None
    
    # ---------------------------------------------------------------------------
    # Implementation of abstract methods
    # ---------------------------------------------------------------------------
    
    def get_channels(self) -> List[Channel]:
        """Return static list of Keshet channels."""
        return [
            Channel(
                id="keshet12",
                name="קשת 12",
                url=f"{self.base_url}/mako-vod-live-tv/VOD-6540b8dcb64fd31006.htm",
                logo="https://img.mako.co.il/2017/06/21/keshet_2017_logo_a.jpg",
                provider=self.provider_name,
            ),
        ]
    
    def get_vods(self, max_items: int = 10) -> List[VOD]:
        """Return VOD items (currently empty, can be implemented later)."""
        vods = []
        try:
            # For simplicity, we'll just return an empty list
            # VOD scraping can be implemented later if needed
            pass
        except Exception as exc:
            self.logger.error("Mako VOD scrape error – %s", exc)
        return vods
    
    def resolve_url(self, url: str, quality: str = "best", prefer_http: bool = True) -> Optional[str]:
        """Main entry point to resolve a URL to a playable stream."""
        return self._play_item(url, quality, switch_cdn=True, prefer_http=prefer_http)
    
    # ---------------------------------------------------------------------------
    # Additional provider-specific methods
    # ---------------------------------------------------------------------------
    
    def get_jellyfin_stream_info(self, url: str) -> Optional[Dict]:
        """Get stream info in a format suitable for Jellyfin."""
        stream_url = self.resolve_url(url, prefer_http=True)
        if not stream_url:
            return None
        
        return {
            "url": stream_url,
            "headers": self.get_headers(),
            "container": "hls",
            "video_codec": "h264",
            "audio_codec": "aac"
        }
    
    def resolve_channel_to_m3u8(self, channel_url: str, channel_name: str = "", 
                              channel_id: str = "", logo: str = "", prefer_http: bool = True) -> str:
        """Resolves a channel URL to an M3U8 playlist entry."""
        stream_url = self.resolve_url(channel_url, prefer_http=prefer_http)
        if not stream_url:
            self.logger.error(f"Failed to resolve {channel_url}")
            return ""
        
        # Create a Channel object and use base class method
        channel = Channel(
            id=channel_id,
            name=channel_name or "Keshet Channel",
            url=stream_url,
            logo=logo,
            provider=self.provider_name
        )
        
        return self.generate_m3u8_entry(channel)
    
    def get_stream_response(self, url: str, prefer_http: bool = True) -> tuple:
        """Helper function for Flask routes that returns appropriate response format."""
        stream_url = self.resolve_url(url, prefer_http=prefer_http)
        if not stream_url:
            return {
                "error": f"Failed to resolve URL: {url}",
                "success": False
            }, 404
        
        return {
            "original_url": url,
            "resolved_url": stream_url,
            "headers": self.get_headers(),
            "success": True
        }
    
    def get_redirect_response(self, url: str, prefer_http: bool = True) -> Any:
        """Helper function for Flask routes that redirects to the resolved stream."""
        stream_url = self.resolve_url(url, prefer_http=prefer_http)
        if not stream_url:
            return {
                "error": f"Failed to resolve URL: {url}",
                "success": False
            }, 404
        
        return stream_url


# ---------------------------------------------------------------------------
# Module-level functions for backward compatibility
# ---------------------------------------------------------------------------

# Create a singleton instance
_provider = KeshetProvider()

def get_channels() -> List[dict]:
    """Get channels as list of dicts for backward compatibility."""
    channels = _provider.get_channels()
    return [
        {
            "id": ch.id,
            "name": ch.name,
            "url": ch.url,
            "logo": ch.logo,
            "provider": ch.provider,
        }
        for ch in channels
    ]

def get_vods(max_items: int = 10) -> List[dict]:
    """Get VODs as list of dicts for backward compatibility."""
    vods = _provider.get_vods(max_items)
    return [
        {
            "id": vod.id,
            "name": vod.name,
            "description": vod.description,
            "url": vod.url,
            "poster": vod.poster,
            "provider": vod.provider,
        }
        for vod in vods
    ]

def resolve_url(url: str, quality: str = "best", prefer_http: bool = False) -> Optional[str]:
    """Resolve URL for backward compatibility."""
    return _provider.resolve_url(url, quality, prefer_http)

def play_item(url: str, quality: str = "best", switch_cdn: bool = False, prefer_http: bool = False) -> Optional[str]:
    """Play item for backward compatibility."""
    return _provider._play_item(url, quality, switch_cdn, prefer_http)

def play(url_params: str, quality: str = "best", switch_cdn: bool = False, prefer_http: bool = False) -> Optional[str]:
    """Play for backward compatibility."""
    return _provider._play(url_params, quality, switch_cdn, prefer_http)

def get_jellyfin_stream_info(url: str) -> Optional[Dict]:
    """Get Jellyfin stream info for backward compatibility."""
    return _provider.get_jellyfin_stream_info(url)

def get_required_headers() -> Dict[str, str]:
    """Get required headers for backward compatibility."""
    return _provider.get_headers()

def generate_m3u8_playlist(prefer_http: bool = True) -> str:
    """Generate M3U8 playlist for backward compatibility."""
    return _provider.generate_playlist(prefer_http=prefer_http)

def resolve_channel_to_m3u8(channel_url: str, channel_name: str = "", channel_id: str = "", 
                           logo: str = "", prefer_http: bool = True) -> str:
    """Resolve channel to M3U8 for backward compatibility."""
    return _provider.resolve_channel_to_m3u8(channel_url, channel_name, channel_id, logo, prefer_http)

def resolve_custom_url_to_m3u8(url: str, name: str = "", prefer_http: bool = True) -> str:
    """Resolve custom URL to M3U8 for backward compatibility."""
    return _provider.resolve_channel_to_m3u8(url, name, prefer_http=prefer_http)

def get_stream_response(url: str, prefer_http: bool = True) -> tuple:
    """Get stream response for backward compatibility."""
    return _provider.get_stream_response(url, prefer_http)

def get_redirect_response(url: str, prefer_http: bool = True) -> Any:
    """Get redirect response for backward compatibility."""
    return _provider.get_redirect_response(url, prefer_http)


__all__ = [
    'KeshetProvider',
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
    # Test using the class
    provider = KeshetProvider()
    
    # Test resolving Keshet 12 channel
    test_url = f"https://www.mako.co.il/mako-vod-live-tv/VOD-6540b8dcb64fd31006.htm"
    
    # Try HTTP version first (preferred for TV compatibility)
    result = provider.resolve_url(test_url, prefer_http=True)
    
    if result:
        print(f"\nSuccessfully resolved URL!")
        print(f"Stream URL: {result}")
        
        # Generate M3U8 entry
        m3u8_entry = provider.resolve_channel_to_m3u8(test_url, "Keshet 12", prefer_http=True)
        print(f"\nM3U8 Entry:\n{m3u8_entry}")
        
        # Show Jellyfin required headers
        print(f"\nRequired Headers for Jellyfin:")
        headers = provider.get_headers()
        for key, value in headers.items():
            print(f"  {key}: {value}")
    else:
        print(f"\nFailed to resolve URL: {test_url}")
        
    # Also show how this would be used in a Flask server
    print("\nFlask Server Example Response:")
    response = provider.get_stream_response(test_url)
    if isinstance(response, tuple):
        print(f"Error: {response[0]}")
    else:
        print(f"Success: {response}")