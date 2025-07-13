from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from yt_dlp import YoutubeDL
import io
import requests
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import re

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

                # Stream with optimized chunks for seeking
                for chunk in r.iter_content(chunk_size=65536):  # 64KB chunks for better seeking
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

@app.get("/view")
async def view_media(
    request: Request,
    url: str = Query(...),
    media_type: str = Query("video"),
    quality: str = Query("medium")
):
    """Stream media with Range request support for seeking in audio/video players"""
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
        'socket_timeout': 15,
        'retries': 1,
        'fragment_retries': 1,
        'http_chunk_size': 2097152,
        'youtube_include_dash_manifest': False,
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

    # Get file size first for Range requests
    head_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    
    try:
        head_response = requests.head(result['url'], headers=head_headers, timeout=10)
        file_size = int(head_response.headers.get('content-length', 0))
    except:
        file_size = 0

    # Parse Range header if present
    range_header = request.headers.get('range')
    start = 0
    end = file_size - 1 if file_size > 0 else None
    
    if range_header:
        range_match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if range_match:
            start = int(range_match.group(1))
            if range_match.group(2):
                end = int(range_match.group(2))

    def stream_with_range():
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive'
            }
            
            # Add Range header for seeking
            if range_header and file_size > 0:
                headers['Range'] = f'bytes={start}-{end}'

            with requests.get(result['url'], stream=True, headers=headers, timeout=20) as r:
                r.raise_for_status()

                # Stream with optimized chunks for seeking
                for chunk in r.iter_content(chunk_size=32768):  # 32KB chunks for smooth seeking
                    if chunk:
                        yield chunk

        except Exception as e:
            yield f"Error: {str(e)}".encode()

    # Determine content type more accurately
    if media_type == 'audio':
        content_type = 'audio/mpeg'
    else:
        content_type = 'video/mp4'

    # Prepare headers for response
    response_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Range, Content-Type, Accept-Ranges",
        "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length"
    }

    # Add Content-Length and Content-Range for proper seeking
    if file_size > 0:
        response_headers["Content-Length"] = str(end - start + 1)
        if range_header:
            response_headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    # Return 206 Partial Content for Range requests
    status_code = 206 if range_header and file_size > 0 else 200

    return StreamingResponse(
        stream_with_range(), 
        status_code=status_code,
        media_type=content_type,
        headers=response_headers
    )

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
            "/view?url=<youtube_url>&media_type=video|audio&quality=low|medium|high - Get direct view URL",
            "/download?url=<youtube_url>&media_type=video|audio&quality=low|medium|high - Download file",
            "/info?url=<youtube_url> - Get video metadata quickly"
        ],
        "performance_tips": [
            "Use /view for reliable streaming through yt-dlp proxy",
            "Use quality=low for fastest streaming",
            "Use /info endpoint to get metadata before streaming"
        ],
        "examples": [
            "/view?url=https://youtu.be/example&media_type=video&quality=medium",
            "/info?url=https://youtu.be/example",
            "/download?url=https://youtu.be/example&media_type=audio&quality=low"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)