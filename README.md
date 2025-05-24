# 🇮🇱 Israeli IPTV Server - Local M3U8 Streaming Solution

[![GitHub stars](https://img.shields.io/github/stars/ak4153/israeli-iptv?style=social)](https://github.com/ak4153/israeli-iptv)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](https://hub.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Jellyfin Compatible](https://img.shields.io/badge/Jellyfin-Compatible-purple)](https://jellyfin.org/)

> **Stream Israeli TV channels locally with ease** - A containerized IPTV server that serves M3U8 playlists for popular Israeli broadcasters including Kan, Keshet, and Reshet 13.

## 🎯 What is Israeli IPTV Server?

This is a lightweight, containerized server that serves `.m3u8` playlist files locally, enabling you to stream Israeli television channels through any IPTV-compatible software such as:

- **Jellyfin** (Media Server)
- **VLC Media Player** 
- **IPTV Smarters**
- **Kodi**
- **Perfect Player**
- Any M3U8-compatible streaming application

![Israeli IPTV Server Demo](https://github.com/user-attachments/assets/00f58bca-7039-4073-b138-ac0c4c5e7e38)

### 📺 Supported Israeli Channels

- **Kan** - Israel's public broadcasting corporation
- **Keshet** - Popular commercial broadcaster  
- **Reshet 13** - Leading news and entertainment network
- **Extensible** - Easy to add more channels via JSON configuration

## 🚀 Quick Start Guide

### Prerequisites

- Docker installed on your system
- Local network access
- IPTV client software (Jellyfin, VLC, etc.)

### 📋 Installation Steps

#### Method 1: Docker Build (Recommended)

```bash
# Clone the repository
git clone https://github.com/ak4153/israeli-iptv.git

# Navigate to project directory  
cd israeli-iptv

# Build Docker image
docker build -t israeli-tv-server .

# Run the container
docker run -p 5000:5000 israeli-tv-server
```

#### Method 2: Docker Compose (For Advanced Users)

Create or add to your existing `docker-compose.yml`:

```yaml
services:
  iptv:
    build:
      context: ./iptv
      dockerfile: Dockerfile
    container_name: israeli-iptv-server
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - ./iptv:/app
    # networks:
    #   - media-network
```

Then run:
```bash
docker-compose up -d
```

## 🎬 Using with Your IPTV Software

Once the server is running, access these M3U8 playlist URLs in your IPTV application:

### 📡 Available Playlist Endpoints

| Channel Group | URL | Description |
|---------------|-----|-------------|
| **Kan Only** | `http://localhost:5000/kan_only.m3u8` | Israel's public broadcasting channels |
| **Keshet Only** | `http://localhost:5000/keshet_only.m3u8` | Keshet Media Group channels |
| **Reshet 13 Only** | `http://localhost:5000/reshet13_only.m3u8` | Channel 13 network streams |

### 🎯 Server Dashboard

Navigate to `http://localhost:5000` in your browser to see the available playlists:

```html
<h1>Israeli TV Playlist Server</h1>
<ul>
  <li><a href="/kan_only.m3u8">/kan_only.m3u8</a> - Kan channels only</li>
  <li><a href="/keshet_only.m3u8">/keshet_only.m3u8</a> - Keshet channels only</li>
  <li><a href="/reshet13_only.m3u8">/reshet13_only.m3u8</a> - Reshet 13 channels only</li>
</ul>
```

### 📱 Jellyfin Integration Example

![Jellyfin IPTV Setup](https://github.com/user-attachments/assets/9f01643c-0eba-4c82-a332-35d5b6ba3929)

1. Open Jellyfin admin dashboard
2. Navigate to **Live TV** settings
3. Add new **M3U Tuner**
4. Enter playlist URL: `http://your-server-ip:5000/kan_only.m3u8`
5. Save and scan for channels

## 🛠️ Development & Contribution

### 🏗️ Architecture

The server uses a modular architecture with:

- **`base_provider.py`** - Abstract class for channel providers
- **`channels.json`** - Channel configuration and M3U8 stream URLs
- **Docker containerization** for easy deployment
- **RESTful API** for playlist serving

### 🤝 Contributing

We welcome contributions! Here's how you can help:

#### Adding New Channels

1. **Fork the repository**
2. **Edit `channels.json`** to add new M3U8 stream URLs
3. **Use `base_provider.py`** abstract class for custom channel providers
4. **Test your changes** locally
5. **Submit a Pull Request**

#### Channel Sources

Current channel data is sourced from the excellent work at:
- [Fishenzon/repo](https://github.com/Fishenzon/repo) - Israeli IPTV streams collection

### 📝 Adding Custom Providers

Creating a new channel provider is straightforward with our modular architecture. Follow these steps:

#### 1. Create Your Provider Class

Extend the `BaseProvider` abstract class and implement the required methods:

```python
# my_provider.py
from typing import List, Optional
from base_provider import BaseProvider, Channel, VOD

class MyCustomProvider(BaseProvider):
    """Custom TV provider implementation."""
    
    # Define your channel data
    CHANNEL_STREAMS = {
        "channel1": {
            "name": "My Channel 1",
            "url": "https://example.com/stream1.m3u8",
            "logo": "https://example.com/logo1.png",
            "referer": "https://example.com/"
        },
        "channel2": {
            "name": "My Channel 2", 
            "url": "https://example.com/stream2.m3u8",
            "logo": "https://example.com/logo2.png"
        }
    }
    
    def __init__(self):
        super().__init__("myprovider")  # Provider name
    
    def get_channels(self) -> List[Channel]:
        """Return list of available channels."""
        channels = []
        for channel_id, data in self.CHANNEL_STREAMS.items():
            channels.append(Channel(
                id=channel_id,
                name=data["name"],
                url=f"myprovider://{channel_id}",  # Custom URL format
                logo=data.get("logo", ""),
                provider=self.provider_name
            ))
        return channels
    
    def get_vods(self, max_items: int = 10) -> List[VOD]:
        """Return list of VOD items (optional)."""
        return []  # Return empty list if no VODs
    
    def resolve_url(self, url: str, quality: str = "best", prefer_http: bool = True) -> Optional[str]:
        """Resolve custom URL to playable stream."""
        if url.startswith("myprovider://"):
            channel_id = url.replace("myprovider://", "")
            if channel_id in self.CHANNEL_STREAMS:
                stream_url = self.CHANNEL_STREAMS[channel_id]["url"]
                # Convert HTTPS to HTTP if preferred
                if prefer_http and stream_url.startswith("https://"):
                    stream_url = stream_url.replace("https://", "http://")
                return stream_url
        return None
    
    def get_headers(self, channel_id: Optional[str] = None) -> dict:
        """Return HTTP headers for requests."""
        headers = super().get_headers(channel_id)
        # Add custom headers if needed
        if channel_id and channel_id in self.CHANNEL_STREAMS:
            referer = self.CHANNEL_STREAMS[channel_id].get("referer")
            if referer:
                headers["Referer"] = referer
        return headers
```

#### 2. Register Your Provider

Add your provider to the main server application:

```python
# In your main app.py or server.py
from my_provider import MyCustomProvider

# Initialize your provider
my_provider = MyCustomProvider()

# Add route for your provider's playlist
@app.route('/myprovider.m3u8')
def myprovider_playlist():
    playlist = my_provider.generate_playlist(prefer_http=True)
    return Response(playlist, mimetype='application/vnd.apple.mpegurl')

# Add to homepage links
provider_links.append({
    'url': '/myprovider.m3u8', 
    'name': 'My Provider Channels'
})
```

#### 3. Advanced Features

**Add VOD Support:**
```python
def get_vods(self, max_items: int = 10) -> List[VOD]:
    vod_data = {
        "movie1": {
            "name": "My Movie",
            "url": "https://example.com/movie.m3u8",
            "poster": "https://example.com/poster.jpg"
        }
    }
    
    vods = []
    for vod_id, data in list(vod_data.items())[:max_items]:
        vods.append(VOD(
            id=vod_id,
            name=data["name"],
            url=f"myprovider://{vod_id}",
            poster=data.get("poster", ""),
            provider=self.provider_name
        ))
    return vods
```

**Add Caching:**
```python
def resolve_url(self, url: str, quality: str = "best", prefer_http: bool = True) -> Optional[str]:
    # Check cache first
    cache_key = f"{url}_{'http' if prefer_http else 'https'}"
    cached_url = self._get_from_link_cache(cache_key)
    if cached_url:
        return cached_url
    
    # Resolve URL logic here...
    resolved_url = "https://example.com/resolved.m3u8"
    
    # Cache the result
    self._set_link_cache(cache_key, resolved_url)
    return resolved_url
```

#### 4. Testing Your Provider

```python
# Test your provider
if __name__ == "__main__":
    provider = MyCustomProvider()
    
    # Test channels
    channels = provider.get_channels()
    print(f"Found {len(channels)} channels")
    
    # Test URL resolution
    for channel in channels:
        resolved = provider.resolve_url(channel.url)
        print(f"{channel.name}: {resolved}")
    
    # Generate playlist
    playlist = provider.generate_playlist()
    print("Generated playlist:")
    print(playlist[:200] + "...")
```

#### 5. Common Provider Patterns

**API-Based Provider:**
```python
import requests

def get_channels(self) -> List[Channel]:
    # Fetch from API
    response = requests.get("https://api.example.com/channels")
    data = response.json()
    
    channels = []
    for item in data["channels"]:
        channels.append(Channel(
            id=item["id"],
            name=item["title"],
            url=f"myprovider://{item['id']}",
            logo=item.get("thumbnail", "")
        ))
    return channels
```

**Dynamic Stream Resolution:**
```python
def resolve_url(self, url: str, quality: str = "best", prefer_http: bool = True) -> Optional[str]:
    channel_id = url.replace("myprovider://", "")
    
    # Make API call to get current stream URL
    api_response = requests.get(f"https://api.example.com/stream/{channel_id}")
    stream_data = api_response.json()
    
    return stream_data.get("stream_url")
```

Your custom provider is now ready! The framework handles M3U8 generation, caching, and HTTP/HTTPS conversion automatically.

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5000` | Server listening port |
| `HOST` | `0.0.0.0` | Server bind address |
| `CHANNELS_FILE` | `channels.json` | Channel configuration file |

### Custom Channel Configuration

Edit `channels.json` to add or modify channels:

```json
{
  "kan": [
    {
      "name": "Kan 11",
      "url": "https://example.com/stream.m3u8",
      "logo": "https://example.com/logo.png"
    }
  ]
}
```

## 🐛 Troubleshooting

### Common Issues

**Port 5000 already in use:**
```bash
docker run -p 8080:5000 israeli-tv-server
```

**Cannot access streams:**
- Verify your network configuration
- Check firewall settings
- Ensure IPTV client supports M3U8 format

**Docker build fails:**
- Update Docker to latest version
- Check available disk space
- Verify internet connection for dependencies

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⭐ Show Your Support

If this project helps you stream Israeli TV channels locally, please consider:

- ⭐ **Starring the repository**
- 🐛 **Reporting bugs** via GitHub Issues
- 💡 **Suggesting features** or improvements
- 🤝 **Contributing code** via Pull Requests
- 📢 **Sharing with others** who might find it useful

## 🔗 Related Projects

- [Jellyfin](https://jellyfin.org/) - Free Software Media System
- [Fishenzon/repo](https://github.com/Fishenzon/repo) - Israeli IPTV streams
- [IPTV Community](https://github.com/iptv-org/iptv) - Global IPTV channels

---

**Made with ❤️ for the Israeli streaming community**

*Keywords: Israeli IPTV, M3U8 streaming, Jellyfin, Docker, Kan, Keshet, Reshet 13, local streaming server, IPTV playlist*
