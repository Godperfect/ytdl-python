
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from yt_dlp import YoutubeDL
import io
import requests
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import re
import random
import time
import hashlib
from typing import Dict, Optional, Tuple
import os

app = FastAPI()

# Random User-Agent pool to avoid bot detection
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
]

# Server-side cache for ultra-fast responses
class VideoCache:
    def __init__(self):
        self.cache: Dict[str, Dict] = {}
        self.timestamps: Dict[str, float] = {}
        self.failed_urls: Dict[str, float] = {}
        self.lock = threading.RLock()
        self.cache_duration = 3600  # 1 hour cache
        self.failed_cache_duration = 300  # 5 minutes for failed URLs
    
    def get_cache_key(self, url: str, quality: str, media_type: str) -> str:
        """Generate cache key for URL + parameters"""
        return hashlib.md5(f"{url}_{quality}_{media_type}".encode()).hexdigest()
    
    def is_failed_recently(self, url: str) -> bool:
        """Check if URL failed recently to avoid retrying"""
        with self.lock:
            if url in self.failed_urls:
                if time.time() - self.failed_urls[url] < self.failed_cache_duration:
                    return True
                else:
                    del self.failed_urls[url]
            return False
    
    def mark_failed(self, url: str):
        """Mark URL as failed to avoid immediate retries"""
        with self.lock:
            self.failed_urls[url] = time.time()
    
    def get(self, cache_key: str) -> Optional[Dict]:
        """Get cached video info if still valid"""
        with self.lock:
            if cache_key in self.cache:
                if time.time() - self.timestamps[cache_key] < self.cache_duration:
                    return self.cache[cache_key]
                else:
                    # Expired cache
                    del self.cache[cache_key]
                    del self.timestamps[cache_key]
            return None
    
    def set(self, cache_key: str, data: Dict):
        """Cache video info"""
        with self.lock:
            self.cache[cache_key] = data
            self.timestamps[cache_key] = time.time()
    
    def clear_old_entries(self):
        """Clear expired cache entries"""
        current_time = time.time()
        with self.lock:
            expired_keys = [
                key for key, timestamp in self.timestamps.items()
                if current_time - timestamp > self.cache_duration
            ]
            for key in expired_keys:
                del self.cache[key]
                del self.timestamps[key]

# Global instances
video_cache = VideoCache()
executor = ThreadPoolExecutor(max_workers=6)

def get_random_user_agent():
    """Return a random user agent to avoid bot detection"""
    return random.choice(USER_AGENTS)

def extract_info_smart(url: str, ydl_opts: Dict, use_cookies: bool = False) -> Dict:
    """Smart extraction with conditional cookie usage and bot detection handling"""
    
    # Try without cookies first (faster)
    try:
        if not use_cookies:
            with YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
    except Exception as e:
        error_msg = str(e).lower()
        
        # Check if error indicates bot detection
        bot_detection_indicators = [
            'sign in to confirm',
            'video unavailable',
            'private video',
            'members-only',
            'age-restricted',
            'login required',
            'verify'
        ]
        
        if any(indicator in error_msg for indicator in bot_detection_indicators):
            print(f"Bot detection detected, trying with cookies for: {url}")
            
            # Try with cookies if available
            if os.path.exists('cookies.txt'):
                cookie_opts = ydl_opts.copy()
                cookie_opts['cookiefile'] = 'cookies.txt'
                try:
                    with YoutubeDL(cookie_opts) as ydl:
                        return ydl.extract_info(url, download=False)
                except Exception as cookie_error:
                    raise HTTPException(
                        status_code=403, 
                        detail=f"Access denied even with authentication: {str(cookie_error)}"
                    )
            else:
                raise HTTPException(
                    status_code=403,
                    detail="Video requires authentication but no cookies available"
                )
        else:
            raise HTTPException(status_code=400, detail=f"Failed to extract video info: {str(e)}")

@app.get("/download")
async def download_media(
    url: str = Query(...),
    media_type: str = Query("video"),
    quality: str = Query("medium")
):
    # Check cache first for instant response
    cache_key = video_cache.get_cache_key(url, quality, media_type)
    cached_result = video_cache.get(cache_key)
    
    if cached_result:
        print(f"Cache HIT for {url} - Instant response!")
        result = cached_result
    else:
        # Check if URL failed recently
        if video_cache.is_failed_recently(url):
            raise HTTPException(status_code=429, detail="URL failed recently, try again later")
        
        print(f"Cache MISS for {url} - Extracting...")
        
        # Ultra-fast format selection
        if media_type == 'audio':
            format_selector = 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio' if quality == 'high' else 'worstaudio[ext=m4a]/worstaudio[ext=webm]/worstaudio'
        else:
            if quality == 'high':
                format_selector = 'best[height<=720][ext=mp4]/best[height<=720]/best'
            elif quality == 'low':
                format_selector = 'worst[height<=360][ext=mp4]/worst[height<=360]/worst'
            else:
                format_selector = 'best[height<=480][ext=mp4]/best[height<=480]/best'

        ydl_opts = {
            'format': format_selector,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
            'simulate': False,
            'socket_timeout': 8,
            'retries': 1,
            'fragment_retries': 1,
            'http_chunk_size': 2097152,
            'youtube_include_dash_manifest': False,
            'postprocessors': [],
        }

        # Extract info asynchronously
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                executor, 
                extract_info_smart, 
                url, 
                ydl_opts, 
                False  # Start without cookies
            )
            
            # Cache successful result
            video_cache.set(cache_key, result)
            print(f"Cached result for {url}")
            
        except Exception as e:
            video_cache.mark_failed(url)
            raise e

    if not result or 'url' not in result:
        raise HTTPException(status_code=404, detail="Video URL not found")

    def stream():
        try:
            headers = {
                'User-Agent': get_random_user_agent(),
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive'
            }

            with requests.get(result['url'], stream=True, headers=headers, timeout=15) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk

        except Exception as e:
            yield f"Error: {str(e)}".encode()

    content_type = 'audio/mpeg' if media_type == 'audio' else 'video/mp4'
    
    # Create a proper filename for download
    title = result.get('title', 'video')
    # Clean title for filename (remove invalid characters)
    safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]  # Limit length
    file_extension = '.mp3' if media_type == 'audio' else '.mp4'
    filename = f"{safe_title}{file_extension}"
    
    return StreamingResponse(
        stream(), 
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "Connection": "keep-alive",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Cache-Status": "HIT" if cached_result else "MISS"
        }
    )

@app.get("/view")
async def view_media(
    request: Request,
    url: str = Query(...),
    media_type: str = Query("video"),
    quality: str = Query("medium")
):
    # Check cache first for instant response
    cache_key = video_cache.get_cache_key(url, quality, media_type)
    cached_result = video_cache.get(cache_key)
    
    if cached_result:
        print(f"Cache HIT for {url} - Instant response!")
        result = cached_result
    else:
        # Check if URL failed recently
        if video_cache.is_failed_recently(url):
            raise HTTPException(status_code=429, detail="URL failed recently, try again later")
        
        print(f"Cache MISS for {url} - Extracting...")
        
        # Ultra-fast format selection
        if media_type == 'audio':
            format_selector = 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio' if quality == 'high' else 'worstaudio[ext=m4a]/worstaudio[ext=webm]/worstaudio'
        else:
            if quality == 'high':
                format_selector = 'best[height<=720][ext=mp4]/best[height<=720]/best'
            elif quality == 'low':
                format_selector = 'worst[height<=360][ext=mp4]/worst[height<=360]/worst'
            else:
                format_selector = 'best[height<=480][ext=mp4]/best[height<=480]/best'

        ydl_opts = {
            'format': format_selector,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
            'simulate': False,
            'socket_timeout': 8,
            'retries': 1,
            'fragment_retries': 1,
            'http_chunk_size': 2097152,
            'youtube_include_dash_manifest': False,
            'postprocessors': [],
        }

        # Extract info asynchronously
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                executor, 
                extract_info_smart, 
                url, 
                ydl_opts, 
                False  # Start without cookies
            )
            
            # Cache successful result
            video_cache.set(cache_key, result)
            print(f"Cached result for {url}")
            
        except Exception as e:
            video_cache.mark_failed(url)
            raise e

    if not result or 'url' not in result:
        raise HTTPException(status_code=404, detail="Video URL not found")

    # Get file size for Range requests
    head_headers = {'User-Agent': get_random_user_agent()}
    try:
        head_response = requests.head(result['url'], headers=head_headers, timeout=8)
        file_size = int(head_response.headers.get('content-length', 0))
    except:
        file_size = 0

    # Parse Range header
    range_header = request.headers.get('range')
    start, end = 0, file_size - 1 if file_size > 0 else None
    
    if range_header:
        range_match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if range_match:
            start = int(range_match.group(1))
            if range_match.group(2):
                end = int(range_match.group(2))

    def stream_with_range():
        try:
            headers = {
                'User-Agent': get_random_user_agent(),
                'Accept': '*/*',
                'Accept-Encoding': 'identity',
                'Connection': 'keep-alive'
            }
            
            if range_header and file_size > 0:
                headers['Range'] = f'bytes={start}-{end}'

            with requests.get(result['url'], stream=True, headers=headers, timeout=15) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=32768):
                    if chunk:
                        yield chunk

        except Exception as e:
            yield f"Error: {str(e)}".encode()

    content_type = 'audio/mpeg' if media_type == 'audio' else 'video/mp4'
    
    response_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Range, Content-Type, Accept-Ranges",
        "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length",
        "X-Cache-Status": "HIT" if cached_result else "MISS"
    }

    if file_size > 0:
        response_headers["Content-Length"] = str(end - start + 1)
        if range_header:
            response_headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    status_code = 206 if range_header and file_size > 0 else 200

    return StreamingResponse(
        stream_with_range(), 
        status_code=status_code,
        media_type=content_type,
        headers=response_headers
    )

@app.get("/info")
async def get_video_info(url: str = Query(...)):
    """Get video metadata with smart caching"""
    # Check cache first
    cache_key = video_cache.get_cache_key(url, "info", "metadata")
    cached_result = video_cache.get(cache_key)
    
    if cached_result:
        return {
            "title": cached_result.get('title', 'Unknown'),
            "duration": cached_result.get('duration', 0),
            "thumbnail": cached_result.get('thumbnail', ''),
            "uploader": cached_result.get('uploader', 'Unknown'),
            "view_count": cached_result.get('view_count', 0),
            "formats_available": len(cached_result.get('formats', [])),
            "cached": True
        }
    
    # Check if URL failed recently
    if video_cache.is_failed_recently(url):
        raise HTTPException(status_code=429, detail="URL failed recently, try again later")

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
        'socket_timeout': 6,
    }

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            executor, 
            extract_info_smart, 
            url, 
            ydl_opts, 
            False
        )
        
        # Cache the result
        video_cache.set(cache_key, result)
        
        return {
            "title": result.get('title', 'Unknown'),
            "duration": result.get('duration', 0),
            "thumbnail": result.get('thumbnail', ''),
            "uploader": result.get('uploader', 'Unknown'),
            "view_count": result.get('view_count', 0),
            "formats_available": len(result.get('formats', [])),
            "cached": False
        }
    except Exception as e:
        video_cache.mark_failed(url)
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/cache/status")
def cache_status():
    """Get cache statistics"""
    with video_cache.lock:
        return {
            "cached_videos": len(video_cache.cache),
            "failed_urls": len(video_cache.failed_urls),
            "cache_duration_hours": video_cache.cache_duration / 3600,
            "cookies_available": os.path.exists('cookies.txt')
        }

@app.post("/cache/clear")
def clear_cache():
    """Clear all cache"""
    with video_cache.lock:
        video_cache.cache.clear()
        video_cache.timestamps.clear()
        video_cache.failed_urls.clear()
    return {"message": "Cache cleared successfully"}

@app.get("/")
def root():
    return {
        "message": "Ultra-Fast YouTube API with Smart Caching & Bot Detection",
        "features": [
            "Server-side caching for instant responses",
            "Smart bot detection with conditional cookie usage",
            "Failed URL tracking to avoid retries",
            "Optimized streaming with Range support"
        ],
        "endpoints": [
            "/view?url=<youtube_url>&media_type=video|audio&quality=low|medium|high",
            "/download?url=<youtube_url>&media_type=video|audio&quality=low|medium|high",
            "/info?url=<youtube_url> - Get video metadata",
            "/cache/status - View cache statistics",
            "/cache/clear - Clear cache (POST)"
        ],
        "performance": [
            "Cached videos return instantly",
            "Cookies used only when bot detection detected",
            "Failed URLs cached to avoid immediate retries",
            "Ultra-fast streaming with optimized chunks"
        ]
    }

# Background task to clean cache periodically
@app.on_event("startup")
async def startup_event():
    """Clean cache on startup"""
    video_cache.clear_old_entries()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
