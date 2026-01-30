import yt_dlp
import os

def test_formats():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    ydl_opts = {
        'listformats': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['tv', 'web', 'android'],
            }
        }
    }
    
    if os.path.exists('youtube_cookies.txt'):
        ydl_opts['cookiefile'] = 'youtube_cookies.txt'
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_formats()
