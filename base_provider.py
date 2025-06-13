# base_provider.py
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
import logging
import time
from dataclasses import dataclass, field

# Set up logging
logger = logging.getLogger(__name__)

@dataclass
class Channel:
    """Data class representing a TV channel."""
    id: str
    name: str
    url: str
    logo: str = ""
    provider: str = ""
    group_title: str = ""
    extra_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class VOD:
    """Data class representing a Video On Demand item."""
    id: str
    name: str
    url: str
    poster: str = ""
    provider: str = ""
    description: str = ""
    extra_data: Dict[str, Any] = field(default_factory=dict)

class BaseProvider(ABC):
    """
    Base class for TV streaming providers.
    
    All TV providers should inherit from this class and implement
    the required abstract methods.
    """
    
    # Default user agent for HTTP requests
    USER_AGENT = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    )
    
    # Cache settings
    LINK_CACHE_TIME = 10 * 60   # 10 minutes for channel/VOD refetchin
    
    def __init__(self, provider_name: str):
        """
        Initialize the provider.
        
        Args:
            provider_name: Name of the provider (e.g., "kan", "keshet", "reshet13")
        """
        self.provider_name = provider_name
        self.logger = logging.getLogger(f"{__name__}.{provider_name}")
        
        # Initialize caches
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._link_cache: Dict[str, Dict[str, Any]] = {}
    
    @abstractmethod
    def get_channels(self) -> List[Channel]:
        """
        Get list of available live channels.
        
        Returns:
            List of Channel objects
        """
        pass
    
    @abstractmethod
    def get_vods(self, max_items: int = 10) -> List[VOD]:
        """
        Get list of available VOD items.
        
        Args:
            max_items: Maximum number of VOD items to return
            
        Returns:
            List of VOD objects
        """
        pass
    
    @abstractmethod
    def resolve_url(self, url: str, quality: str = "best", prefer_http: bool = True) -> Optional[str]:
        """
        Resolve a provider-specific URL to a playable stream URL.
        
        Args:
            url: The URL to resolve (can be custom format like "provider://channel_id")
            quality: Desired quality (default: "best")
            prefer_http: Whether to prefer HTTP over HTTPS for compatibility
            
        Returns:
            The resolved playable URL or None if resolution fails
        """
        pass
    
    def get_headers(self, channel_id: Optional[str] = None) -> Dict[str, str]:
        """
        Get HTTP headers required for playback.
        
        Args:
            channel_id: Optional channel ID for channel-specific headers
            
        Returns:
            Dictionary of HTTP headers
        """
        return {
            "User-Agent": self.USER_AGENT
        }
    
    def generate_m3u8_entry(self, channel: Channel, use_headers: bool = True) -> str:
        """
        Generate an M3U8 playlist entry for a channel.
        
        Args:
            channel: Channel object
            use_headers: Whether to include EXTVLCOPT headers
            
        Returns:
            M3U8 formatted entry string
        """
        # Build the EXTINF line
        extinf_parts = ["#EXTINF:-1"]
        
        if channel.id:
            extinf_parts.append(f'tvg-id="{channel.id}"')
        if channel.logo:
            extinf_parts.append(f'tvg-logo="{channel.logo}"')
        if channel.group_title:
            extinf_parts.append(f'group-title="{channel.group_title}"')
        elif self.provider_name:
            extinf_parts.append(f'group-title="{self.provider_name.title()}"')
        
        entry = f"{' '.join(extinf_parts)},{channel.name}\n"
        
        # Add headers if requested
        if use_headers:
            headers = self.get_headers(channel.id)
            if "User-Agent" in headers:
                entry += f'#EXTVLCOPT:http-user-agent={headers["User-Agent"]}\n'
            if "Referer" in headers:
                entry += f'#EXTVLCOPT:http-referrer={headers["Referer"]}\n'
        
        # Add the URL
        entry += f'{channel.url}\n'
        
        return entry
    
    def generate_playlist(self, prefer_http: bool = True, include_vods: bool = False) -> str:
        """
        Generate a complete M3U8 playlist for this provider.
        
        Args:
            prefer_http: Whether to prefer HTTP URLs
            include_vods: Whether to include VOD items in the playlist
            
        Returns:
            M3U8 formatted playlist string
        """
        playlist = "#EXTM3U\n"
        
        # Add channels
        for channel in self.get_channels():
            # Resolve the URL if needed
            if channel.url.startswith(f"{self.provider_name}://"):
                resolved_url = self.resolve_url(channel.url, prefer_http=prefer_http)
                if resolved_url:
                    channel.url = resolved_url
                else:
                    self.logger.warning(f"Failed to resolve {channel.url}")
                    continue
            
            playlist += self.generate_m3u8_entry(channel)
        
        # Add VODs if requested
        if include_vods:
            for vod in self.get_vods():
                # Convert VOD to Channel for M3U8 generation
                channel = Channel(
                    id=f"{self.provider_name}-vod-{vod.id}",
                    name=vod.name,
                    url=vod.url,
                    logo=vod.poster,
                    provider=vod.provider or self.provider_name,
                    group_title=f"{self.provider_name.title()} VOD"
                )
                
                # Resolve URL if needed
                if channel.url.startswith(f"{self.provider_name}://"):
                    resolved_url = self.resolve_url(channel.url, prefer_http=prefer_http)
                    if resolved_url:
                        channel.url = resolved_url
                    else:
                        self.logger.warning(f"Failed to resolve VOD {channel.url}")
                        continue
                
                playlist += self.generate_m3u8_entry(channel)
        
        return playlist
    
    def _is_cache_valid(self, cache_entry: Dict[str, Any], ttl: int) -> bool:
        """
        Check if a cache entry is still valid.
        
        Args:
            cache_entry: Cache entry dictionary with 't' timestamp
            ttl: Time to live in seconds
            
        Returns:
            True if cache is still valid
        """
        if not cache_entry or 't' not in cache_entry:
            return False
        return time.time() - cache_entry['t'] < ttl
    
    def _get_from_cache(self, key: str, ttl: Optional[int] = None) -> Optional[Any]:
        """
        Get value from cache if still valid.
        
        Args:
            key: Cache key
            ttl: Time to live in seconds (default: LINK_CACHE_TIME)
            
        Returns:
            Cached value or None
        """
        if ttl is None:
            ttl = self.LINK_CACHE_TIME
            
        cache_entry = self._cache.get(key)
        if cache_entry and self._is_cache_valid(cache_entry, ttl):
            return cache_entry.get('data')
        return None
    
    def _set_cache(self, key: str, data: Any) -> None:
        """
        Store value in cache with current timestamp.
        
        Args:
            key: Cache key
            data: Data to cache
        """
        self._cache[key] = {
            'data': data,
            't': time.time()
        }
    
    def _get_from_link_cache(self, key: str) -> Optional[str]:
        """
        Get resolved URL from link cache if still valid.
        
        Args:
            key: Cache key (usually the original URL)
            
        Returns:
            Cached URL or None
        """
        cache_entry = self._link_cache.get(key)
        if cache_entry and self._is_cache_valid(cache_entry, self.LINK_CACHE_TIME):
            self.logger.info(f"Cache hit for {key} in link cache for {cache_entry.get('url')}")
            return cache_entry.get('url')
        return None
    
    def _set_link_cache(self, key: str, url: str) -> None:
        """
        Store resolved URL in link cache.
        
        Args:
            key: Cache key (usually the original URL)
            url: Resolved URL to cache
        """
        self._link_cache[key] = {
            'url': url,
            't': time.time()
        }
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        self._cache.clear()
        self._link_cache.clear()
        self.logger.info(f"Cleared all caches for {self.provider_name}")