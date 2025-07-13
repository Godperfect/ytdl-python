from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from yt_dlp import YoutubeDL
import io
import requests
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

app = FastAPI()

# Global thread pool for non-blocking operations
executor = ThreadPoolExecutor(max_workers=4)

def extract_info_fast(url, ydl_opts):
    """Extract video info in a separate thread for faster response"""
    try:
        with YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract video info: {str(e)}")

@app.get("/download")
async def download_media(
    url: str = Query(...),
    media_type: str = Query("video"),
    quality: str = Query("medium")
):
    # Ultra-fast format selection for immediate streaming
    if media_type == 'audio':
        if quality == 'high':
            format_selector = 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio'
        else:
            format_selector = 'worstaudio[ext=m4a]/worstaudio[ext=webm]/worstaudio'
    else:
        if quality == 'high':
            format_selector = 'best[height<=720][ext=mp4]/best[height<=720]/best'
        elif quality == 'low':
            format_selector = 'worst[height<=360][ext=mp4]/worst[height<=360]/worst'
        else:  # medium
            format_selector = 'best[height<=480][ext=mp4]/best[height<=480]/best'

    ydl_opts = {
        'format': format_selector,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'simulate': False,
        'socket_timeout': 15,  # Reduced timeout
        'retries': 1,  # Faster failure recovery
        'fragment_retries': 1,
        'http_chunk_size': 2097152,  # 2MB chunks
        'youtube_include_dash_manifest': False,  # Skip DASH for speed
        'postprocessors': [],
    }

    # Extract info asynchronously for faster response
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(executor, extract_info_fast, url, ydl_opts)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not result or 'url' not in result:
        raise HTTPException(status_code=404, detail="Video URL not found")

    def stream():
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive'
            }
            
            with requests.get(result['url'], stream=True, headers=headers, timeout=20) as r:
                r.raise_for_status()
                
                # Optimized chunk size for faster streaming
                for chunk in r.iter_content(chunk_size=131072):  # 128KB chunks
                    if chunk:
                        yield chunk
                        
        except Exception as e:
            yield f"Error: {str(e)}".encode()

    # Determine content type more accurately
    if media_type == 'audio':
        content_type = 'audio/mpeg'
        filename = f"audio.mp3"
    else:
        content_type = 'video/mp4'
        filename = f"video.mp4"
    
    return StreamingResponse(
        stream(), 
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "Connection": "keep-alive"
        }
    )

@app.get("/stream")
async def stream_media(
    url: str = Query(...),
    media_type: str = Query("video"),
    quality: str = Query("medium")
):
    """Stream media directly for playback in your Next.js app"""
    # Same format selection as download but optimized for streaming
    if media_type == 'audio':
        if quality == 'high':
            format_selector = 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio'
        else:
            format_selector = 'worstaudio[ext=m4a]/worstaudio[ext=webm]/worstaudio'
    else:
        if quality == 'high':
            format_selector = 'best[height<=720][ext=mp4]/best[height<=720]/best'
        elif quality == 'low':
            format_selector = 'worst[height<=360][ext=mp4]/worst[height<=360]/worst'
        else:
            format_selector = 'best[height<=480][ext=mp4]/best[height<=480]/best'

    ydl_opts = {
        'format': format_selector,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 10,
        'youtube_include_dash_manifest': False,
    }

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(executor, extract_info_fast, url, ydl_opts)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not result or 'url' not in result:
        raise HTTPException(status_code=404, detail="Video URL not found")

    # Return the direct stream URL for your Next.js app to use
    return {
        "stream_url": result['url'],
        "title": result.get('title', 'Unknown'),
        "duration": result.get('duration', 0),
        "thumbnail": result.get('thumbnail', ''),
        "format": result.get('ext', 'mp4'),
    }

@app.get("/info")
async def get_video_info(url: str = Query(...)):
    """Get video metadata quickly for your Next.js frontend"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
        'socket_timeout': 10,
    }
    
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(executor, extract_info_fast, url, ydl_opts)
        return {
            "title": result.get('title', 'Unknown'),
            "duration": result.get('duration', 0),
            "thumbnail": result.get('thumbnail', ''),
            "uploader": result.get('uploader', 'Unknown'),
            "view_count": result.get('view_count', 0),
            "formats_available": len(result.get('formats', [])),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/")
def root():
    return {
        "message": "Ultra-Fast YouTube Streaming API for Next.js",
        "endpoints": [
            "/stream?url=<youtube_url>&media_type=video|audio&quality=low|medium|high - Get direct stream URL",
            "/download?url=<youtube_url>&media_type=video|audio&quality=low|medium|high - Download file",
            "/info?url=<youtube_url> - Get video metadata quickly"
        ],
        "performance_tips": [
            "Use /stream for direct playback in your Next.js app",
            "Use quality=low for fastest streaming",
            "Use /info endpoint to get metadata before streaming"
        ],
        "examples": [
            "/stream?url=https://youtu.be/example&media_type=video&quality=medium",
            "/info?url=https://youtu.be/example",
            "/download?url=https://youtu.be/example&media_type=audio&quality=low"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)