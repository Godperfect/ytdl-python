from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from yt_dlp import YoutubeDL
import os
import tempfile
import io

app = FastAPI()

@app.get("/download")
def download_media(
    url: str = Query(...),
    media_type: str = Query("video")
):
    try:
        # Create a temporary directory for downloads
        temp_dir = tempfile.mkdtemp()
        
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best[height<=720]' if media_type == 'audio' else 'best[height<=720]/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'restrictfilenames': True,
            'cookiefile': None,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            },
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls']
                }
            },
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }] if media_type == 'audio' else [],
        }

        with YoutubeDL(ydl_opts) as ydl:
            # Extract info first
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown')
            duration = info.get('duration', 0)
            uploader = info.get('uploader', 'Unknown')
            
            # Now download the file
            ydl.download([url])
            
            # Find the downloaded file
            files = os.listdir(temp_dir)
            if not files:
                raise HTTPException(status_code=500, detail="Download failed")
            
            downloaded_file = os.path.join(temp_dir, files[0])
            
            # Determine content type and filename
            if media_type == 'audio':
                content_type = 'audio/mpeg'
                filename = f"{title}.mp3"
            else:
                content_type = 'video/mp4'
                filename = f"{title}.mp4"
            
            # Read file into memory
            with open(downloaded_file, 'rb') as f:
                file_content = f.read()
            
            # Clean up temp file
            os.remove(downloaded_file)
            os.rmdir(temp_dir)
            
            # Return streaming response
            return StreamingResponse(
                io.BytesIO(file_content),
                media_type=content_type,
                headers={
                    "Content-Disposition": f"attachment; filename=\"{filename}\"",
                    "Content-Length": str(len(file_content))
                }
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading: {str(e)}")

@app.get("/info")
def get_media_info(url: str = Query(...)):
    """Get media information without downloading"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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
        "message": "YouTube Downloader API", 
        "endpoints": [
            "/download?url=<youtube_url>&media_type=video|audio - Download media file",
            "/info?url=<youtube_url> - Get media information"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)