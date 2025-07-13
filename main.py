from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from yt_dlp import YoutubeDL
import os
import tempfile
import io
import random
import time
from fake_useragent import UserAgent

app = FastAPI()

def get_bypass_config():
    """Get configuration with multiple bypass techniques"""
    ua = UserAgent()
    
    # List of working proxies (you can add free proxy services)
    proxies = [
        None,  # No proxy as fallback
        # Add working proxies here if available
    ]
    
    return {
        'user_agent': ua.random,
        'proxy': random.choice(proxies),
        'delay': random.uniform(1, 3)
    }

@app.get("/download")
def download_media(
    url: str = Query(...),
    media_type: str = Query("video")
):
    # Try multiple bypass methods
    methods = [
        {'name': 'standard', 'config': get_bypass_config()},
        {'name': 'mobile', 'config': get_bypass_config()},
        {'name': 'embedded', 'config': get_bypass_config()}
    ]
    
    for method in methods:
        try:
            temp_dir = tempfile.mkdtemp()
            config = method['config']
            
            # Add delay to avoid rate limiting
            time.sleep(config['delay'])
            
            ydl_opts = {
                'format': 'worst[height<=360]/bestaudio[ext=m4a]/bestaudio' if media_type == 'audio' else 'worst[height<=360]/best',
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'restrictfilenames': True,
                'no_check_certificate': True,
                'ignoreerrors': True,
                'http_headers': {
                    'User-Agent': config['user_agent'],
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Cache-Control': 'max-age=0',
                },
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash', 'hls'] if method['name'] == 'standard' else [],
                        'player_skip': ['configs'],
                        'player_client': ['android', 'web'] if method['name'] == 'mobile' else ['web'],
                    }
                },
                'geo_bypass': True,
                'geo_bypass_country': 'US',
                'age_limit': None,
                'sleep_interval': 1,
                'max_sleep_interval': 3,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }] if media_type == 'audio' else [],
            }
            
            # Add proxy if available
            if config['proxy']:
                ydl_opts['proxy'] = config['proxy']
            
            # Special handling for embedded method
            if method['name'] == 'embedded':
                # Try to extract from embedded player
                if 'youtu.be/' in url or 'youtube.com/watch' in url:
                    video_id = url.split('/')[-1].split('?')[0] if 'youtu.be/' in url else url.split('v=')[1].split('&')[0]
                    url = f"https://www.youtube.com/embed/{video_id}"
                    ydl_opts['http_headers']['Referer'] = 'https://www.youtube.com/'

            with YoutubeDL(ydl_opts) as ydl:
                # Extract info first
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown')
                
                # Now download the file
                ydl.download([url])
                
                # Find the downloaded file
                files = os.listdir(temp_dir)
                if not files:
                    continue  # Try next method
                
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
            # Clean up and try next method
            try:
                if os.path.exists(temp_dir):
                    for file in os.listdir(temp_dir):
                        os.remove(os.path.join(temp_dir, file))
                    os.rmdir(temp_dir)
            except:
                pass
            continue
    
    # If all methods failed
    raise HTTPException(status_code=500, detail="All bypass methods failed. Video may be region-locked or require authentication.")

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
        
        if config['proxy']:
            ydl_opts['proxy'] = config['proxy']
        
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