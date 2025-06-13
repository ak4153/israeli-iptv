# reshet13_module.py
import requests
import logging
from urllib.parse import urlparse, parse_qs
from typing import List, Optional, Dict

from base_provider import BaseProvider, Channel, VOD

# Set up logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Reshet13Provider(BaseProvider):
    """Reshet 13 (Channel 13) TV provider implementation."""
    
    # Channel 13 stream data
    CHANNEL_13_STREAMS = {
        "13b": {
            "referer": "https://13tv.co.il/live/",
            "link": "https://d18b0e6mopany4.cloudfront.net/out/v1/2f2bc414a3db4698a8e94b89eaf2da2a/index.m3u8"
        },
        "13b2": {
            "klt": "1_pjrmtdaf",
            "link": "https://d2xg1g9o5vns8m.cloudfront.net/out/v1/0855d703f7d5436fae6a9c7ce8ca5075/index.m3u8",
            "referer": "https://13tv.co.il/allshows/2010263/"
        },
        "13c": {
            "referer": "https://13tv.co.il/live/",
            "link": "https://reshet.g-mana.live/media/4607e158-e4d4-4e18-9160-3dc3ea9bc677/mainManifest.m3u8"
        },
        "bb": {
            "brv": "videoId",
            "cst": "26",
            "klt": "1_6fr5xbw2",
            "referer": "https://13tv.co.il/home/bb-livestream/",
            "link": "https://d2lckchr9cxrss.cloudfront.net/out/v1/c73af7694cce4767888c08a7534b503c/index.m3u8"
        },
        "13comedy": {
            "klt": "adsadadas",
            "link": "https://d15ds134q59udk.cloudfront.net/out/v1/fbba879221d045598540ee783b140fe2/index.m3u8",
            "referer": "https://13tv.co.il/allshows/2605018/"
        },
        "13nofesh": {
            "klt": "1_g7lqf2yg",
            "link": "https://d1yd8hohnldm33.cloudfront.net/out/v1/19dee23c2cc24f689bd4e1288661ee0c/index.m3u8",
            "referer": "https://13tv.co.il/allshows/2395628/"
        },
        "13reality": {
            "klt": "1_khfzmmtx",
            "link": "https://d2dffl3588mvfk.cloudfront.net/out/v1/d8e15050ca4148aab0ee387a5e2eb46b/index.m3u8",
            "referer": "https://13tv.co.il/allshows/2395629/"
        }
    }
    
    # Channel logos and names
    CHANNEL_LOGOS = {
        "13": "https://upload.wikimedia.org/wikipedia/he/thumb/2/2e/Reshet_13_logo.svg/1200px-Reshet_13_logo.svg.png",
        "13b": "https://upload.wikimedia.org/wikipedia/he/thumb/2/2e/Reshet_13_logo.svg/1200px-Reshet_13_logo.svg.png",
        "13c": "https://upload.wikimedia.org/wikipedia/he/thumb/2/2e/Reshet_13_logo.svg/1200px-Reshet_13_logo.svg.png",
        "bb": "https://img.mako.co.il/2023/01/15/bigblogo_aa.png",
        "13comedy": "https://img.mako.co.il/2020/08/04/COMEDY_LOGO0_a.jpg",
        "13nofesh": "https://img.mako.co.il/2020/08/04/ADVENTURE_LOGO_a.jpg",
        "13reality": "https://img.mako.co.il/2020/08/04/REALITY_LOGO0_a.jpg",
        "13b2": "https://upload.wikimedia.org/wikipedia/he/thumb/2/2e/Reshet_13_logo.svg/1200px-Reshet_13_logo.svg.png"
    }
    
    CHANNEL_NAMES = {
        "13": "Channel 13",
        "13b": "Channel 13B",
        "13c": "Channel 13C",
        "bb": "Big Brother",
        "13comedy": "13 Comedy",
        "13nofesh": "13 Nofesh",
        "13reality": "13 Reality",
        "13b2": "13B2"
    }
    
    def __init__(self):
        super().__init__("reshet13")
    
    # ---------------------------------------------------------------------------
    # Implementation of abstract methods
    # ---------------------------------------------------------------------------
    
    def get_channels(self) -> List[Channel]:
        """Return a list of available Channel 13 channels."""
        channels = []
        
        # Add main channels
        for channel_id in ["13", "13b", "13c", "bb"]:
            if channel_id in self.CHANNEL_13_STREAMS:
                channels.append(Channel(
                    id=channel_id,
                    name=self.CHANNEL_NAMES.get(channel_id, f"Channel {channel_id}"),
                    url=f"reshet13://{channel_id}",
                    logo=self.CHANNEL_LOGOS.get(channel_id, ""),
                    provider=self.provider_name,
                ))
        
        return channels
    
    def get_vods(self, max_items: int = 10) -> List[VOD]:
        """Return a list of Channel 13 VOD channels."""
        vods = []
        
        # Add VOD channels
        for channel_id in ["13comedy", "13nofesh", "13reality", "13b2"]:
            if channel_id in self.CHANNEL_13_STREAMS:
                vods.append(VOD(
                    id=channel_id,
                    name=self.CHANNEL_NAMES.get(channel_id, f"Channel {channel_id}"),
                    url=f"reshet13://{channel_id}",
                    poster=self.CHANNEL_LOGOS.get(channel_id, ""),
                    provider=self.provider_name,
                ))
        
        return vods
    
    def resolve_url(self, url: str, quality: str = "best", prefer_http: bool = True) -> Optional[str]:
        """
        Resolve a Channel 13 URL to a playable stream URL.
        
        Args:
            url: The URL to resolve (format: reshet13://{channel_id})
            quality: Desired quality (not used for Reshet13)
            prefer_http: Whether to prefer HTTP over HTTPS for TV compatibility
            
        Returns:
            The resolved playable URL or None if resolution fails
        """
        try:
            # Check link cache first
            cache_key = f"{url}_{'http' if prefer_http else 'https'}"
            cached_url = self._get_from_link_cache(cache_key)
            if cached_url:
                return cached_url
            
            # Parse the custom URL format
            if url.startswith("reshet13://"):
                channel_id = url.replace("reshet13://", "")
                
                # Check if the channel exists in our stream data
                if channel_id not in self.CHANNEL_13_STREAMS:
                    self.logger.error(f"Unknown Channel 13 channel ID: {channel_id}")
                    return None
                
                # Get the stream data
                stream_data = self.CHANNEL_13_STREAMS[channel_id]
                
                # Get the stream URL and modify protocol if necessary
                stream_url = stream_data["link"]
                if prefer_http and stream_url.startswith("https://"):
                    stream_url = stream_url.replace("https://", "http://")
                
                self.logger.info(f"Resolved Channel 13 URL '{url}' to '{stream_url}'")
                
                # Cache the resolved URL
                self._set_link_cache(cache_key, stream_url)
                
                return stream_url
            else:
                self.logger.error(f"Invalid Channel 13 URL format: {url}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error resolving Channel 13 URL: {str(e)}")
            return None
    
    def get_headers(self, channel_id: Optional[str] = None) -> Dict[str, str]:
        """
        Get the necessary headers for a channel.
        
        Args:
            channel_id: The channel ID
            
        Returns:
            Dictionary of HTTP headers
        """
        headers = super().get_headers(channel_id)
        
        # Add Referer header if present in channel data
        if channel_id and channel_id in self.CHANNEL_13_STREAMS:
            stream_data = self.CHANNEL_13_STREAMS[channel_id]
            if "referer" in stream_data:
                headers["Referer"] = stream_data["referer"]
        
        return headers
    
    # ---------------------------------------------------------------------------
    # Additional provider-specific methods
    # ---------------------------------------------------------------------------
    
    def get_stream_details(self, channel_id: str) -> Optional[Dict]:
        """
        Get all details for a stream including URL and headers.
        
        Args:
            channel_id: The channel ID
            
        Returns:
            Dictionary with stream details including URL and headers
        """
        if channel_id not in self.CHANNEL_13_STREAMS:
            return None
        
        stream_data = self.CHANNEL_13_STREAMS[channel_id]
        
        details = {
            "url": stream_data["link"],
            "headers": self.get_headers(channel_id)
        }
        
        return details


# ---------------------------------------------------------------------------
# Module-level functions for backward compatibility
# ---------------------------------------------------------------------------

# Create a singleton instance
_provider = Reshet13Provider()

def get_channels() -> List[dict]:
    """Get channels as list of dicts for backward compatibility."""
    channels = _provider.get_channels()
    return [
        {
            "id": ch.id,
            "name": ch.name,
            "url": ch.url,
            "logo": ch.logo,
        }
        for ch in channels
    ]

def get_vods() -> List[dict]:
    """Get VODs as list of dicts for backward compatibility."""
    vods = _provider.get_vods()
    return [
        {
            "id": vod.id,
            "name": vod.name,
            "poster": vod.poster,
            "url": vod.url,
        }
        for vod in vods
    ]

def resolve_url(url: str, prefer_http: bool = True) -> Optional[str]:
    """Resolve URL for backward compatibility."""
    return _provider.resolve_url(url, prefer_http=prefer_http)

def get_channel_headers(channel_id: str) -> Dict[str, str]:
    """Get channel headers for backward compatibility."""
    return _provider.get_headers(channel_id)

def get_stream_details(channel_id: str) -> Optional[Dict]:
    """Get stream details for backward compatibility."""
    return _provider.get_stream_details(channel_id)


__all__ = [
    'Reshet13Provider',
    'get_channels',
    'get_vods',
    'resolve_url',
    'get_channel_headers',
    'get_stream_details',
]


# Testing function to verify the module works
def test():
    """Test the module functionality."""
    provider = Reshet13Provider()
    
    print("Channel 13 Channels:")
    for ch in provider.get_channels():
        print(f"- {ch.name} ({ch.id}): {ch.url}")
        resolved_url = provider.resolve_url(ch.url)
        print(f"  Resolved to: {resolved_url}")
    
    print("\nChannel 13 VODs:")
    for vod in provider.get_vods():
        print(f"- {vod.name} ({vod.id}): {vod.url}")
        resolved_url = provider.resolve_url(vod.url)
        print(f"  Resolved to: {resolved_url}")
    
    print("\nGenerated M3U8 Playlist:")
    playlist = provider.generate_playlist(prefer_http=True, include_vods=True)
    print(playlist[:500] + "..." if len(playlist) > 500 else playlist)


if __name__ == "__main__":
    test()