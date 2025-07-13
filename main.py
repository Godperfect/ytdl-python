from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from yt_dlp import YoutubeDL
import os
import tempfile
import random
import time
from fake_useragent import UserAgent
import shutil

app = FastAPI()

def get_bypass_config():
    """Get configuration with multiple bypass techniques"""
    ua = UserAgent()

    return {
        'user_agent': ua.random,
        'delay': random.uniform(0.5, 2)
    }

def download_and_stream(url, media_type):
    """Download media using yt-dlp and stream it"""
    config = get_bypass_config()
    time.sleep(config['delay'])

    temp_dir = tempfile.mkdtemp()

    try:
        # Configure yt-dlp options for reliable downloads
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best' if media_type == 'audio' else 'best[height<=720]/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'restrictfilenames': True,
            'no_check_certificate': True,
            'geo_bypass': True,
            'http_headers': {
                'User-Agent': config['user_agent'],
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web'],
                    'skip': ['dash', 'hls']
                }
            },
        }

        # Add audio-specific post-processing
        if media_type == 'audio':
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]

        with YoutubeDL(ydl_opts) as ydl:
            # Extract info first
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown')
            duration = info.get('duration', 0)

            # Download the media
            ydl.download([url])

            # Find the downloaded file
            downloaded_files = os.listdir(temp_dir)
            if not downloaded_files:
                raise Exception("No files were downloaded")

            downloaded_file = os.path.join(temp_dir, downloaded_files[0])

            # Determine content type and filename
            if media_type == 'audio':
                content_type = 'audio/mpeg'
                filename = f"{title}.mp3"
            else:
                content_type = 'video/mp4'
                filename = f"{title}.mp4"

            # Create a streaming generator
            def file_streamer():
                try:
                    with open(downloaded_file, 'rb') as f:
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            yield chunk
                finally:
                    # Clean up temporary files
                    try:
                        shutil.rmtree(temp_dir)
                    except:
                        pass

            return {
                'generator': file_streamer(),
                'content_type': content_type,
                'filename': filename,
                'title': title,
                'duration': duration
            }

    except Exception as e:
        # Clean up on error
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
        raise Exception(f"Download failed: {str(e)}")

@app.get("/download")
def download_media(
    url: str = Query(...),
    media_type: str = Query("video")
):
    try:
        # Download and get stream info
        stream_info = download_and_stream(url, media_type)

        # Return streaming response for download
        return StreamingResponse(
            stream_info['generator'],
            media_type=stream_info['content_type'],
            headers={
                "Content-Disposition": f"attachment; filename=\"{stream_info['filename']}\"",
                "Cache-Control": "no-cache"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stream")
def stream_media(
    url: str = Query(...),
    media_type: str = Query("video")
):
    """Stream media directly without download headers"""
    try:
        # Download and get stream info
        stream_info = download_and_stream(url, media_type)

        # Return streaming response for direct playback
        return StreamingResponse(
            stream_info['generator'],
            media_type=stream_info['content_type'],
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/info")
def get_media_info(url: str = Query(...)):
    """Get media information without downloading"""
    config = get_bypass_config()
    time.sleep(config['delay'])

    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': config['user_agent'],
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            'geo_bypass': True,
            'no_check_certificate': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                }
            },
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting info: {str(e)}")

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