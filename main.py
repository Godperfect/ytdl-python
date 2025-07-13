
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from yt_dlp import YoutubeDL
import os
import tempfile
import random
import time
from fake_useragent import UserAgent
import requests
from urllib.parse import urlparse

app = FastAPI()

def get_bypass_config():
    """Get configuration with multiple bypass techniques"""
    ua = UserAgent()
    
    return {
        'user_agent': ua.random,
        'delay': random.uniform(0.5, 2)
    }

def get_stream_url(url, media_type):
    """Extract direct stream URL from video URL"""
    config = get_bypass_config()
    time.sleep(config['delay'])
    
    # Try multiple extraction methods
    methods = [
        {
            'name': 'android_client',
            'client': 'android',
            'format': 'bestaudio[ext=m4a]/bestaudio/worst[height<=480]' if media_type == 'audio' else 'best[height<=720]/worst[height<=480]'
        },
        {
            'name': 'ios_client', 
            'client': 'ios',
            'format': 'bestaudio/worst[height<=360]' if media_type == 'audio' else 'best[height<=480]/worst[height<=360]'
        },
        {
            'name': 'web_client',
            'client': 'web',
            'format': 'bestaudio[ext=webm]/bestaudio/worst' if media_type == 'audio' else 'worst[height<=360]/best'
        }
    ]
    
    for method in methods:
        try:
            ydl_opts = {
                'format': method['format'],
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'no_check_certificate': True,
                'ignoreerrors': True,
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
                        'player_client': [method['client']],
                        'skip': ['dash', 'hls'] if method['name'] == 'web_client' else [],
                        'player_skip': ['js', 'configs'] if method['client'] != 'web' else []
                    }
                },
                'geo_bypass': True,
                'age_limit': None,
            }
            
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if info and 'url' in info:
                    return {
                        'stream_url': info['url'],
                        'title': info.get('title', 'Unknown'),
                        'duration': info.get('duration', 0),
                        'content_type': 'audio/mp4' if media_type == 'audio' else 'video/mp4'
                    }
                
                # If no direct URL, check formats
                formats = info.get('formats', [])
                if formats:
                    # Filter formats based on media type
                    if media_type == 'audio':
                        audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                        if audio_formats:
                            selected = audio_formats[0]
                        else:
                            selected = formats[0]
                    else:
                        video_formats = [f for f in formats if f.get('vcodec') != 'none']
                        if video_formats:
                            selected = sorted(video_formats, key=lambda x: x.get('height', 0))[0]
                        else:
                            selected = formats[0]
                    
                    if selected and 'url' in selected:
                        return {
                            'stream_url': selected['url'],
                            'title': info.get('title', 'Unknown'),
                            'duration': info.get('duration', 0),
                            'content_type': selected.get('ext', 'mp4')
                        }
                        
        except Exception as e:
            print(f"Method {method['name']} failed: {str(e)}")
            continue
    
    return None

def stream_from_url(stream_url, content_type):
    """Stream content from URL with proper headers"""
    ua = UserAgent()
    headers = {
        'User-Agent': ua.random,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'identity',
        'Range': 'bytes=0-',
        'Connection': 'keep-alive',
    }
    
    try:
        response = requests.get(stream_url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        
        def generate():
            try:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            except Exception as e:
                print(f"Streaming error: {e}")
            finally:
                response.close()
        
        return generate()
    except Exception as e:
        print(f"Stream request failed: {e}")
        return None

@app.get("/download")
def download_media(
    url: str = Query(...),
    media_type: str = Query("video")
):
    try:
        # Get stream URL
        stream_info = get_stream_url(url, media_type)
        
        if not stream_info:
            raise HTTPException(status_code=500, detail="Could not extract stream URL. Video may be restricted or unavailable.")
        
        # Get streaming generator
        stream_generator = stream_from_url(stream_info['stream_url'], stream_info['content_type'])
        
        if not stream_generator:
            raise HTTPException(status_code=500, detail="Could not establish stream connection.")
        
        # Determine content type and filename
        if media_type == 'audio':
            content_type = 'audio/mp4'
            filename = f"{stream_info['title']}.m4a"
        else:
            content_type = 'video/mp4'
            filename = f"{stream_info['title']}.mp4"
        
        # Return streaming response
        return StreamingResponse(
            stream_generator,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Streaming failed: {str(e)}")

@app.get("/stream")
def stream_media(
    url: str = Query(...),
    media_type: str = Query("video")
):
    """Stream media directly without download headers"""
    try:
        # Get stream URL
        stream_info = get_stream_url(url, media_type)
        
        if not stream_info:
            raise HTTPException(status_code=500, detail="Could not extract stream URL. Video may be restricted or unavailable.")
        
        # Get streaming generator
        stream_generator = stream_from_url(stream_info['stream_url'], stream_info['content_type'])
        
        if not stream_generator:
            raise HTTPException(status_code=500, detail="Could not establish stream connection.")
        
        # Determine content type
        if media_type == 'audio':
            content_type = 'audio/mp4'
        else:
            content_type = 'video/mp4'
        
        # Return streaming response for direct playback
        return StreamingResponse(
            stream_generator,
            media_type=content_type,
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Streaming failed: {str(e)}")

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
