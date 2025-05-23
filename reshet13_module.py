import requests
import logging
from urllib.parse import urlparse, parse_qs

# Set up logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
)

# Channel 13 stream data
CHANNEL_13_STREAMS = {
    "13": {
        "referer": "https://13tv.co.il/live/",
        "link": "https://reshet.g-mana.live/media/87f59c77-03f6-4bad-a648-897e095e7360/mainManifest.m3u8"
    },
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

def get_channels():
    """Return a list of available Channel 13 channels."""
    channels = []
    
    # Add main channels
    for channel_id in ["13", "13b", "13c", "bb"]:
        if channel_id in CHANNEL_13_STREAMS:
            channels.append({
                "id": channel_id,
                "name": CHANNEL_NAMES.get(channel_id, f"Channel {channel_id}"),
                "logo": CHANNEL_LOGOS.get(channel_id, ""),
                "url": f"reshet13://{channel_id}",
            })
    
    return channels

def get_vods():
    """Return a list of Channel 13 VOD channels."""
    vods = []
    
    # Add VOD channels
    for channel_id in ["13comedy", "13nofesh", "13reality", "13b2"]:
        if channel_id in CHANNEL_13_STREAMS:
            vods.append({
                "id": channel_id,
                "name": CHANNEL_NAMES.get(channel_id, f"Channel {channel_id}"),
                "poster": CHANNEL_LOGOS.get(channel_id, ""),
                "url": f"reshet13://{channel_id}",
            })
    
    return vods

def resolve_url(url, prefer_http=True):
    """
    Resolve a Channel 13 URL to a playable stream URL.
    
    Args:
        url (str): The URL to resolve (format: reshet13://{channel_id})
        prefer_http (bool): Whether to prefer HTTP over HTTPS for TV compatibility
        
    Returns:
        str: The resolved playable URL or None if resolution fails
    """
    try:
        # Parse the custom URL format
        if url.startswith("reshet13://"):
            channel_id = url.replace("reshet13://", "")
            
            # Check if the channel exists in our stream data
            if channel_id not in CHANNEL_13_STREAMS:
                logger.error(f"Unknown Channel 13 channel ID: {channel_id}")
                return None
            
            # Get the stream data
            stream_data = CHANNEL_13_STREAMS[channel_id]
            
            # Get the stream URL and modify protocol if necessary
            stream_url = stream_data["link"]
            if prefer_http and stream_url.startswith("https://"):
                stream_url = stream_url.replace("https://", "http://")
            
            logger.info(f"Resolved Channel 13 URL '{url}' to '{stream_url}'")
            return stream_url
        else:
            logger.error(f"Invalid Channel 13 URL format: {url}")
            return None
            
    except Exception as e:
        logger.error(f"Error resolving Channel 13 URL: {str(e)}")
        return None

def get_channel_headers(channel_id):
    """
    Get the necessary headers for a channel.
    
    Args:
        channel_id (str): The channel ID
        
    Returns:
        dict: A dictionary of headers
    """
    headers = {
        "User-Agent": USER_AGENT,
    }
    
    # Add Referer header if present in channel data
    if channel_id in CHANNEL_13_STREAMS and "referer" in CHANNEL_13_STREAMS[channel_id]:
        headers["Referer"] = CHANNEL_13_STREAMS[channel_id]["referer"]
    
    return headers

def get_stream_details(channel_id):
    """
    Get all details for a stream including URL and headers.
    
    Args:
        channel_id (str): The channel ID
        
    Returns:
        dict: A dictionary with stream details including URL and headers
    """
    if channel_id not in CHANNEL_13_STREAMS:
        return None
    
    stream_data = CHANNEL_13_STREAMS[channel_id]
    
    details = {
        "url": stream_data["link"],
        "headers": get_channel_headers(channel_id)
    }
    
    return details

# Testing function to verify the module works
def test():
    """Test the module functionality."""
    print("Channel 13 Channels:")
    for ch in get_channels():
        print(f"- {ch['name']} ({ch['id']}): {ch['url']}")
        resolved_url = resolve_url(ch['url'])
        print(f"  Resolved to: {resolved_url}")
    
    print("\nChannel 13 VODs:")
    for vod in get_vods():
        print(f"- {vod['name']} ({vod['id']}): {vod['url']}")
        resolved_url = resolve_url(vod['url'])
        print(f"  Resolved to: {resolved_url}")

if __name__ == "__main__":
    test()
