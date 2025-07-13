from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from yt_dlp import YoutubeDL
import io
import requests

app = FastAPI()

@app.get("/download")
def download_media(
    url: str = Query(...),
    media_type: str = Query("video"),
    quality: str = Query("medium")
):
    # Optimize format selection for speed
    if media_type == 'audio':
        if quality == 'high':
            format_selector = 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio'
        else:
            format_selector = 'worstaudio[ext=m4a]/worstaudio[ext=mp3]/worstaudio'
    else:
        if quality == 'high':
            format_selector = 'best[height<=720][ext=mp4]/best[ext=mp4]/best'
        elif quality == 'low':
            format_selector = 'worst[height<=480][ext=mp4]/worst[ext=mp4]/worst'
        else:  # medium
            format_selector = 'best[height<=480][ext=mp4]/best[ext=mp4]/best'

    ydl_opts = {
        'format': format_selector,
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
        'socket_timeout': 30,
        'retries': 3,
        'fragment_retries': 3,
        'http_chunk_size': 1048576,  # 1MB chunks for faster streaming
        'postprocessors': [] if media_type == 'video' else [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128' if quality == 'low' else '192',
        }],
    }

    def stream():
        with YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
            if 'url' in result:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': '*/*',
                    'Accept-Encoding': 'identity',
                    'Range': 'bytes=0-'
                }
                r = requests.get(result['url'], stream=True, headers=headers, timeout=30)
                r.raise_for_status()
                
                # Use larger chunks for faster streaming
                for chunk in r.iter_content(chunk_size=65536):  # 64KB chunks
                    if chunk:
                        yield chunk

    content_type = 'audio/mpeg' if media_type == 'audio' else 'video/mp4'
    return StreamingResponse(stream(), media_type=content_type)

@app.get("/")
def root():
    return {
        "message": "YouTube Downloader API",
        "endpoints": [
            "/download?url=<youtube_url>&media_type=video|audio&quality=low|medium|high"
        ],
        "examples": [
            "/download?url=https://youtu.be/example&media_type=audio&quality=medium",
            "/download?url=https://youtu.be/example&media_type=video&quality=low"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)