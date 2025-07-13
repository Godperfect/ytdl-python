from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from yt_dlp import YoutubeDL
import io
import requests
import random

app = FastAPI()

# SOCKS5 proxy configuration
PROXY_CONFIG = {
    'protocol': 'socks5',
    'port': 1080,
    'username': 'PKksJImNm9m',
    'password': '1dL56jWydrO',
    'hosts': [
        'mel.socks.ipvanish.com',  # Australia
        'tor.socks.ipvanish.com',  # Canada
        'lin.socks.ipvanish.com',  # Italy
        'ams.socks.ipvanish.com',  # Netherlands
        'waw.socks.ipvanish.com',  # Poland
        'sin.socks.ipvanish.com',  # Singapore
        'mad.socks.ipvanish.com',  # Spain
        'lon.socks.ipvanish.com',  # UK
    ]
}

def get_random_proxy():
    """Get a random proxy from the available hosts"""
    host = random.choice(PROXY_CONFIG['hosts'])
    return f"socks5://{PROXY_CONFIG['username']}:{PROXY_CONFIG['password']}@{host}:{PROXY_CONFIG['port']}"

@app.get("/download")
def download_media(
    url: str = Query(...),
    media_type: str = Query("video")
):
    proxy_url = get_random_proxy()

    ydl_opts = {
        'format': 'bestaudio/best' if media_type == 'audio' else 'best',
        'noplaylist': True,
        'quiet': True,
        'outtmpl': '-',
        'no_warnings': True,
        'extract_flat': False,
        'force_generic_extractor': False,
        'simulate': False,
        'restrictfilenames': True,
        'logtostderr': False,
        'cachedir': False,
        'proxy': proxy_url,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }] if media_type == 'audio' else [],
    }

    def stream():
        with YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
            if 'url' in result:
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
                r = requests.get(result['url'], stream=True, proxies=proxies)
                for chunk in r.iter_content(chunk_size=8192):
                    yield chunk

    content_type = 'audio/mpeg' if media_type == 'audio' else 'video/mp4'
    return StreamingResponse(stream(), media_type=content_type)

@app.get("/stream")
def stream_media(
    url: str = Query(...),
    media_type: str = Query("video")
):
    """Stream media directly without download headers"""
    proxy_url = get_random_proxy()

    ydl_opts = {
        'format': 'bestaudio/best' if media_type == 'audio' else 'best',
        'noplaylist': True,
        'quiet': True,
        'outtmpl': '-',
        'no_warnings': True,
        'extract_flat': False,
        'force_generic_extractor': False,
        'simulate': False,
        'restrictfilenames': True,
        'logtostderr': False,
        'cachedir': False,
        'proxy': proxy_url,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }] if media_type == 'audio' else [],
    }

    def stream():
        with YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
            if 'url' in result:
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
                r = requests.get(result['url'], stream=True, proxies=proxies)
                for chunk in r.iter_content(chunk_size=8192):
                    yield chunk

    content_type = 'audio/mpeg' if media_type == 'audio' else 'video/mp4'
    return StreamingResponse(
        stream(), 
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache"
        }
    )

@app.get("/info")
def get_media_info(url: str = Query(...)):
    """Get media information without downloading"""
    proxy_url = get_random_proxy()

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'proxy': proxy_url,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        return {
            "title": info.get('title', 'Unknown'),
            "duration": info.get('duration', 0),
            "uploader": info.get('uploader', 'Unknown'),
            "description": info.get('description', ''),
            "view_count": info.get('view_count', 0),
            "upload_date": info.get('upload_date', ''),
            "thumbnail": info.get('thumbnail', ''),
            "formats_available": len(info.get('formats', []))
        }

@app.get("/")
def root():
    return {
        "message": "YouTube Streaming API", 
        "endpoints": [
            "/download?url=<youtube_url>&media_type=video|audio - Download media file",
            "/stream?url=<youtube_url>&media_type=video|audio - Stream media directly",
            "/info?url=<youtube_url> - Get media information"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)