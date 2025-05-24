# What is this
This is a server that serves `.m3u8` files locally, which can be used to stream IPTV Israeli channels on an IPTV software such as Jellyfin
![image](https://github.com/user-attachments/assets/00f58bca-7039-4073-b138-ac0c4c5e7e38)

# How to use
I like to containerize everything I can so should you:

`git clone https://github.com/ak4153/israeli-iptv.git` </br>
`cd israeli-iptv` </br>
`docker build -t israeli-tv-server .` </br>
`docker run -p 5000:5000` </br>

### You can also add it to orchestrate it with docker-compose
```
 iptv:
    build:
      context: ./iptv
      dockerfile: Dockerfile
    container_name: iptv
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - ./iptv:/app
#    networks:
#      - media-network
```

Now you can add the m3u8 URLS inside your IPTV software that runs on your local network

        '<h1>Israeli TV Playlist Server</h1>'
        '<ul>'
        '<li><a href="/kan_only.m3u8">/kan_only.m3u8</a> - Kan channels only</li>'
        '<li><a href="/keshet_only.m3u8">/keshet_only.m3u8</a> - Keshet channels only</li>'
        '<li><a href="/reshet13_only.m3u8">/reshet13_only.m3u8</a> - Reshet 13 channels only</li>'
        '</ul>'
![image](https://github.com/user-attachments/assets/9f01643c-0eba-4c82-a332-35d5b6ba3929)

I use Jellyfin, but you can use anything else like IPTV Smarters or anyother effective app.

# Contribute
You can use the `base_provider.py` abstract class as an API to create your own channels.
You can use `channels.json` that contains links to `.m3u8` streams (which I took from https://github.com/Fishenzon/repo) to add more IPTV channles.

Feel free to make a PR I will merge ASAP.
