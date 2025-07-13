    from fastapi import FastAPI, Query
    from fastapi.responses import StreamingResponse
    from yt_dlp import YoutubeDL
    import io

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
            'outtmpl': '-',
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

        buffer = io.BytesIO()

        def stream():
            with YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(url, download=False)
                if 'url' in result:
                    import requests
                    r = requests.get(result['url'], stream=True)
                    for chunk in r.iter_content(chunk_size=8192):
                        yield chunk

        content_type = 'audio/mpeg' if media_type == 'audio' else 'video/mp4'
        return StreamingResponse(stream(), media_type=content_type)