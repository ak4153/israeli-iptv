# kan_module.py
import os
import re
import json
import time
import logging
import requests
from urllib.parse import quote_plus, unquote_plus, urlparse, parse_qs
from typing import List, Optional

from base_provider import BaseProvider, Channel, VOD

# Configure logging for the module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ---------------------------------------------------------------------------
# Constants – Kan
# ---------------------------------------------------------------------------
KAN_BASE_URL = 'https://www.kan.org.il'
KAN_BASE_KIDS_URL = 'https://www.kankids.org.il'
KAN_ARCHIVE_URL = 'https://archive.kan.org.il'
KAN_BASE_MOB_API_URL = 'https://mobapi.kan.org.il'
KAN_MOBAPI = 'https://mobapi.kan.org.il/api/mobile/subClass'


class KanProvider(BaseProvider):
    """Kan TV provider implementation."""
    
    def __init__(self):
        super().__init__("kan")
        self.base_url = KAN_BASE_URL
        self.base_kids_url = KAN_BASE_KIDS_URL
        self.archive_url = KAN_ARCHIVE_URL
        self.base_mob_api_url = KAN_BASE_MOB_API_URL
        self.mobapi = KAN_MOBAPI
    
    # ---------------------------------------------------------------------------
    # Helper utilities (private methods)
    # ---------------------------------------------------------------------------
    
    def _get_cf(self, url: str, timeout: int = 30) -> str:
        """Fetch *url* with basic Cloudflare‑protected site tolerance."""
        try:
            headers = self.get_headers()
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code != 200:
                self.logger.warning("%s → HTTP %s", url, r.status_code)
                return ""
            return r.text
        except Exception as exc:
            self.logger.error("Kan fetch error for %s – %s", url, exc)
            return ""
    
    def _get_cached(self, url: str, ttl: int = None) -> str:
        """Get URL content with caching."""
        if ttl is None:
            ttl = self.CACHE_TIME
            
        # Check cache first
        cached = self._get_from_cache(url, ttl)
        if cached is not None:
            return cached
            
        # Fetch and cache
        body = self._get_cf(url)
        if body:
            self._set_cache(url, body)
        return body
    
    def _get_json(self, url: str):
        """Get JSON from URL."""
        try:
            headers = self.get_headers()
            r = requests.get(url, headers=headers)
            if r.status_code != 200:
                self.logger.warning("JSON %s → HTTP %s", url, r.status_code)
                return None
            return r.json().get('root') or r.json()
        except Exception as exc:
            self.logger.error("Kan JSON error for %s – %s", url, exc)
            return None
    
    def _get_json_script(self, url: str):
        """Extract inline JSON from HTML page."""
        html = self._get_cached(url)
        try:
            import json as _json
            m = re.search(r'type="application/json">(.*?)</script>', html)
            return _json.loads(m.group(1)) if m else None
        except Exception as exc:
            self.logger.debug("No inline JSON on %s – %s", url, exc)
            return None
    
    # ---------------------------------------------------------------------------
    # Implementation of abstract methods
    # ---------------------------------------------------------------------------
    
    def get_channels(self) -> List[Channel]:
        """Return static list of Kan live channels."""
        return [
            Channel(
                id="kan11",
                name="כאן 11",
                url="https://kan11.media.kan.org.il/hls/live/2024514/2024514/master.m3u8",
                logo="https://www.kan.org.il/images/logo_kan.jpg",
                provider=self.provider_name,
            ),
            Channel(
                id="makan",
                name="מכאן",
                url="https://makan.media.kan.org.il/hls/live/2024680/2024680/master.m3u8",
                logo="https://www.kan.org.il/images/logo_makan.jpg",
                provider=self.provider_name,
            ),
            Channel(
                id="kan_educational",
                name="כאן חינוכית",
                url="https://kan23.media.kan.org.il/hls/live/2024691/2024691/master.m3u8",
                logo="https://www.kan.org.il/media/1749/23tv.jpg",
                provider=self.provider_name,
            ),
        ]
    
    def get_vods(self, max_items: int = 10) -> List[VOD]:
        """Return a handful of featured VOD items scraped from Kan lobby."""
        vods: List[VOD] = []
        try:
            content = self._get_cached(f"{self.base_url}/lobby/kan11")
            block_m = re.search(r'<div class="vod-section(.*?)<div class="section-content">', content, re.S)
            if not block_m:
                return vods
                
            item_rx = re.compile(
                r'<div aria-label="(.*?)">.*?url\((.*?)">.*?<div class="info-description">(.*?)</div>\s*<a href="(.*?)"',
                re.S,
            )
            
            for name, img, desc, href in item_rx.findall(block_m.group(1))[:max_items]:
                page = href if href.startswith('http') else f"{self.base_url}{href}"
                media_url = self.resolve_url(page)  # eager resolve for playlist
                if not media_url:
                    continue
                    
                vods.append(VOD(
                    id=page.split('/')[-1],
                    name=name.strip(),
                    description=desc.strip(),
                    url=media_url,
                    poster=img if img.startswith('http') else f"{self.base_url}{img}",
                    provider=self.provider_name,
                ))
        except Exception as exc:
            self.logger.error("Kan VOD scrape error %s", exc)
        return vods
    
    def resolve_url(self, page_url: str, quality: str = "best", prefer_http: bool = True) -> Optional[str]:
        """Return a playable HLS/embed URL extracted from a Kan page."""
        # Check link cache first
        cached_url = self._get_from_link_cache(page_url)
        if cached_url:
            return cached_url
        
        # Process URL
        url = page_url.replace('https', 'http') if prefer_http else page_url
        i = url.rfind('http://')
        if i > 0:
            url = url[i:]
        url = url.replace('HLS/HLS', 'HLS')
        
        text = self._get_cached(url)
        resolved: Optional[str] = None
        
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
                    self.logger.debug("Kaltura parse error %s", exc)
        
        # Handle protocol preference
        if resolved and prefer_http and resolved.startswith('https://'):
            resolved = resolved.replace('https://', 'http://')
        
        # Cache the resolved URL
        if resolved:
            self._set_link_cache(page_url, resolved)
            
        return resolved


# ---------------------------------------------------------------------------
# Module-level functions for backward compatibility
# ---------------------------------------------------------------------------

# Create a singleton instance
_provider = KanProvider()

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

def resolve_url(page_url: str) -> Optional[str]:
    """Resolve URL for backward compatibility."""
    return _provider.resolve_url(page_url)


__all__ = [
    'KanProvider',
    'get_channels',
    'get_vods',
    'resolve_url',
]


# If run directly, test the provider
if __name__ == "__main__":
    # Test using the class
    provider = KanProvider()
    
    print("Testing KanProvider class:")
    print("\nChannels:")
    for channel in provider.get_channels():
        print(f"- {channel.name} ({channel.id}): {channel.url}")
    
    print("\nVODs (first 3):")
    for vod in provider.get_vods(3):
        print(f"- {vod.name}: {vod.url}")
    
    print("\nGenerated M3U8 Playlist:")
    playlist = provider.generate_playlist(prefer_http=True, include_vods=False)
    print(playlist[:500] + "..." if len(playlist) > 500 else playlist)
