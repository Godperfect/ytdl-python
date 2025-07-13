from fastapi import FastAPI, Query
from yt_dlp import YoutubeDL

app = FastAPI()

@app.get("/download")
def download_media(
    url: str = Query(...),
    media_type: str = Query("video")
):
    ydl_opts = {
        'format': 'bestaudio/best' if media_type == 'audio' else 'best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'force_generic_extractor': False,
        'simulate': False,
        'restrictfilenames': True,
        'logtostderr': False,
        'cachedir': False,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }] if media_type == 'audio' else [],
    }

    with YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(url, download=False)

        if 'url' in result:
            return {
                "direct_url": result['url'],
                "title": result.get('title', 'Unknown'),
                "duration": result.get('duration', 0),
                "uploader": result.get('uploader', 'Unknown'),
                "media_type": media_type
            }
        else:
            return {"error": "Could not extract video URL"}

@app.get("/")
def root():
    return {"message": "YouTube Downloader API", "endpoints": ["/download?url=<youtube_url>&media_type=video|audio"]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)