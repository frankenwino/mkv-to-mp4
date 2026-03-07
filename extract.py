#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
import requests
from dotenv import load_dotenv

load_dotenv()

# Apple TV target codec (H.264 for maximum compatibility)
APPLE_TV_VIDEO_CODEC = 'h264'
APPLE_TV_AUDIO_CODECS = {'aac', 'ac3', 'eac3'}
APPLE_TV_SUBTITLE_CODECS = {'mov_text', 'srt', 'subrip', 'ass', 'ssa', 'dvb_subtitle'}
SUPPORTED_VIDEO_FORMATS = {'.mkv', '.mp4', '.avi', '.wmv', '.flv', '.mov', '.m4v', '.ts', '.webm', '.mpg', '.mpeg'}

TVDB_API_KEY = os.getenv('TVDB_API_KEY')
TVDB_BASE_URL = 'https://api4.thetvdb.com/v4'
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
TMDB_ACCESS_TOKEN = os.getenv('TMDB_ACCESS_TOKEN')
TMDB_BASE_URL = 'https://api.themoviedb.org/3'
TMDB_IMAGE_BASE_URL = None  # Will be fetched from configuration

def get_tvdb_token():
    """Get authentication token from TVDB API."""
    if not TVDB_API_KEY:
        return None
    try:
        response = requests.post(f'{TVDB_BASE_URL}/login', json={'apikey': TVDB_API_KEY}, timeout=10)
        if response.status_code == 200:
            return response.json()['data']['token']
    except Exception as e:
        log(f"TVDB auth failed: {e}", verbose=True)
    return None

def search_tvdb_series(show_name, token):
    """Search for TV series on TVDB."""
    if not token:
        return None
    try:
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get(f'{TVDB_BASE_URL}/search', params={'query': show_name, 'type': 'series'}, headers=headers, timeout=10)
        if response.status_code == 200:
            results = response.json()['data']
            if results:
                return results[0]['tvdb_id']
    except Exception as e:
        log(f"TVDB search failed: {e}", verbose=True)
    return None

def get_tvdb_episode(series_id, season, episode, token):
    """Get episode details from TVDB."""
    if not token:
        return None
    try:
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get(f'{TVDB_BASE_URL}/series/{series_id}/episodes/default', params={'season': season, 'episodeNumber': episode}, headers=headers, timeout=10)
        if response.status_code == 200:
            episodes = response.json()['data']['episodes']
            if episodes:
                return episodes[0]
    except Exception as e:
        log(f"TVDB episode fetch failed: {e}", verbose=True)
    return None

def get_tvdb_series_artwork(series_id, token):
    """Get series artwork from TVDB (poster)."""
    if not token:
        return None
    try:
        headers = {'Authorization': f'Bearer {token}'}
        # Type 2 is poster (portrait)
        response = requests.get(f'{TVDB_BASE_URL}/series/{series_id}/artworks', params={'lang': 'eng', 'type': 2}, headers=headers, timeout=10)
        if response.status_code == 200:
            artworks = response.json()['data']['artworks']
            if artworks and artworks[0].get('image'):
                return artworks[0]['image']
    except Exception as e:
        log(f"TVDB artwork fetch failed: {e}", verbose=True)
    return None

def download_image(url, token):
    """Download image from TVDB."""
    if not url or not token:
        return None
    try:
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        log(f"Image download failed: {e}", verbose=True)
    return None

def get_tmdb_configuration():
    """Get TMDB configuration including image base URL."""
    global TMDB_IMAGE_BASE_URL
    if TMDB_IMAGE_BASE_URL:
        return TMDB_IMAGE_BASE_URL
    
    if not TMDB_ACCESS_TOKEN:
        return None
    try:
        headers = {'Authorization': f'Bearer {TMDB_ACCESS_TOKEN}'}
        response = requests.get(f'{TMDB_BASE_URL}/configuration', headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            TMDB_IMAGE_BASE_URL = data['images']['secure_base_url'] + 'original'
            return TMDB_IMAGE_BASE_URL
    except Exception as e:
        log(f"TMDB configuration fetch failed: {e}", verbose=True)
    return None

def search_tmdb_movie(title, year=None):
    """Search for movie on TMDB."""
    if not TMDB_ACCESS_TOKEN:
        return None
    try:
        headers = {'Authorization': f'Bearer {TMDB_ACCESS_TOKEN}'}
        params = {'query': title}
        if year:
            params['year'] = year
        response = requests.get(f'{TMDB_BASE_URL}/search/movie', params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            results = response.json()['results']
            if results:
                return results[0]['id']
    except Exception as e:
        log(f"TMDB search failed: {e}", verbose=True)
    return None

def get_tmdb_movie_details(movie_id):
    """Get movie details from TMDB."""
    if not TMDB_ACCESS_TOKEN:
        return None
    try:
        headers = {'Authorization': f'Bearer {TMDB_ACCESS_TOKEN}'}
        response = requests.get(f'{TMDB_BASE_URL}/movie/{movie_id}', headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        log(f"TMDB movie details fetch failed: {e}", verbose=True)
    return None

def download_tmdb_image(poster_path):
    """Download image from TMDB."""
    if not poster_path:
        return None
    
    base_url = get_tmdb_configuration()
    if not base_url:
        return None
    
    try:
        image_url = f"{base_url}{poster_path}"
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        log(f"TMDB image download failed: {e}", verbose=True)
    return None

def check_handbrake_cli():
    """Check if HandBrakeCLI is available."""
    try:
        result = subprocess.run(['HandBrakeCLI', '--version'], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def partial_hash(file_path, chunk_size=65536):
    """Generate partial hash of file (first, middle, last chunks) for duplicate detection."""
    try:
        file_size = os.path.getsize(file_path)
        hasher = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            # Hash first chunk
            hasher.update(f.read(chunk_size))
            
            # Hash middle chunk if file is large enough
            if file_size > chunk_size * 2:
                f.seek(file_size // 2)
                hasher.update(f.read(chunk_size))
            
            # Hash last chunk if file is large enough
            if file_size > chunk_size:
                f.seek(max(0, file_size - chunk_size))
                hasher.update(f.read(chunk_size))
        
        return hasher.hexdigest()
    except Exception as e:
        log(f"Failed to hash {file_path}: {e}", verbose=True)
        return None

def log(msg, verbose=False, force=False):
    if force or verbose:
        print(msg)

def parse_filename(filename):
    """Parse TV show or movie information from filename."""
    basename = Path(filename).stem
    
    # TV Show pattern with year: Show.Name.YYYY.SXXEXX
    tv_pattern_year = r'^(.+?)[.\s]+(\d{4})[.\s]+S(\d+)E(\d+)[.\s]+(.+?)(?:\.\d{3,4}p|$)'
    match = re.match(tv_pattern_year, basename, re.IGNORECASE)
    
    if match:
        show_name = match.group(1).replace('.', ' ')
        year = match.group(2)
        season = int(match.group(3))
        episode = int(match.group(4))
        episode_title = match.group(5).replace('.', ' ')
        
        return {
            'type': 'tv',
            'show': show_name,
            'year': year,
            'season': season,
            'episode': episode,
            'episode_title': episode_title
        }
    
    # TV Show pattern without year: Show.Name.SXXEXX
    tv_pattern_no_year = r'^(.+?)[.\s]+S(\d+)E(\d+)[.\s]+(.+?)(?:\.\d{3,4}p|$)'
    match = re.match(tv_pattern_no_year, basename, re.IGNORECASE)
    
    if match:
        show_name = match.group(1).replace('.', ' ')
        season = int(match.group(2))
        episode = int(match.group(3))
        episode_title = match.group(4).replace('.', ' ')
        
        return {
            'type': 'tv',
            'show': show_name,
            'year': None,
            'season': season,
            'episode': episode,
            'episode_title': episode_title
        }
    
    # Movie pattern: Movie.Name.YEAR
    movie_pattern = r'^(.+?)[.\s]+(\d{4})'
    match = re.match(movie_pattern, basename, re.IGNORECASE)
    
    if match:
        movie_name = match.group(1).replace('.', ' ')
        year = match.group(2)
        
        return {
            'type': 'movie',
            'title': movie_name,
            'year': year
        }
    
    return {
        'type': 'unknown',
        'filename': basename
    }

def probe_file(mkv_path):
    """Probe file and return stream information."""
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', mkv_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)

def extract_file_metadata(file_path):
    """Extract metadata tags from video file (title, year, artist, etc.)."""
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    
    try:
        data = json.loads(result.stdout)
        tags = data.get('format', {}).get('tags', {})
        
        # Extract useful metadata
        metadata = {}
        if tags.get('title'):
            metadata['title'] = tags['title']
        if tags.get('date'):
            # Try to extract year from date field
            try:
                year_str = tags['date']
                if len(year_str) >= 4:
                    metadata['year'] = int(year_str[:4])
            except:
                pass
        if tags.get('artist'):
            metadata['artist'] = tags['artist']
        if tags.get('genre'):
            metadata['genre'] = tags['genre']
        
        return metadata
    except:
        return {}

def check_compatibility(streams):
    """Check if streams are Apple TV compatible."""
    compatible = []
    incompatible = []
    
    for stream in streams.get('streams', []):
        codec = stream.get('codec_name', '').lower()
        stream_type = stream.get('codec_type', '')
        
        if stream_type == 'video':
            if codec == APPLE_TV_VIDEO_CODEC:
                compatible.append(stream)
            else:
                incompatible.append((stream_type, codec))
        elif stream_type == 'audio':
            if codec in APPLE_TV_AUDIO_CODECS:
                compatible.append(stream)
            else:
                incompatible.append((stream_type, codec))
        elif stream_type == 'subtitle':
            if codec in APPLE_TV_SUBTITLE_CODECS:
                compatible.append(stream)
            else:
                incompatible.append((stream_type, codec))
    
    return compatible, incompatible

def display_tracks(streams):
    """Display available tracks and return selection."""
    print("\nAvailable tracks:")
    for idx, stream in enumerate(streams, 1):
        stream_type = stream.get('codec_type', 'unknown')
        codec = stream.get('codec_name', 'unknown')
        lang = stream.get('tags', {}).get('language', 'und')
        title = stream.get('tags', {}).get('title', '')
        
        info = f"[{idx}] {stream_type.upper()}: {codec}"
        if lang != 'und':
            info += f" ({lang})"
        if title:
            info += f" - {title}"
        print(info)
    
    # Auto-select: all video, all audio, only English/Swedish subtitles (excluding dvb_subtitle which can't be in MP4)
    auto_selected = []
    for idx, stream in enumerate(streams):
        stream_type = stream.get('codec_type')
        codec = stream.get('codec_name', '')
        lang = stream.get('tags', {}).get('language', 'und')
        
        if stream_type == 'video':
            auto_selected.append(idx)
        elif stream_type == 'audio':
            auto_selected.append(idx)
        elif stream_type == 'subtitle':
            # Skip dvb_subtitle as it's not compatible with MP4 container
            if lang in ['eng', 'swe'] and codec != 'dvb_subtitle':
                auto_selected.append(idx)
    
    if auto_selected:
        selected_nums = [str(i + 1) for i in auto_selected]
        print(f"Auto-selected: {', '.join(selected_nums)} (video + all audio + English/Swedish subs, excluding dvb_subtitle)")
    
    return auto_selected

def extract_streams(mkv_path, output_path, selected_streams, info, image_data, verbose=False):
    """Extract selected streams to MP4."""
    cmd = ['ffmpeg', '-i', mkv_path]
    
    # Add image as input if available
    image_input_idx = None
    if image_data:
        image_path = '/tmp/tvdb_poster.jpg'
        with open(image_path, 'wb') as f:
            f.write(image_data)
        cmd.extend(['-i', image_path])
        image_input_idx = 1
    
    for stream in selected_streams:
        stream_idx = stream['index']
        cmd.extend(['-map', f'0:{stream_idx}'])
    
    # Map image as cover art
    if image_input_idx:
        cmd.extend(['-map', f'{image_input_idx}:0'])
    
    # Set codec for each stream type
    video_idx = 0
    audio_idx = 0
    subtitle_idx = 0
    
    for stream in selected_streams:
        codec_type = stream.get('codec_type')
        codec_name = stream.get('codec_name')
        
        if codec_type == 'video':
            cmd.extend([f'-c:v:{video_idx}', 'copy'])
            video_idx += 1
        elif codec_type == 'audio':
            cmd.extend([f'-c:a:{audio_idx}', 'copy'])
            audio_idx += 1
        elif codec_type == 'subtitle':
            if codec_name in ['subrip', 'srt', 'ass', 'ssa']:
                # Convert text-based subtitles to mov_text for MP4
                cmd.extend([f'-c:s:{subtitle_idx}', 'mov_text'])
            else:
                cmd.extend([f'-c:s:{subtitle_idx}', 'copy'])
            subtitle_idx += 1
    
    # Set cover art codec
    if image_input_idx:
        cmd.extend([f'-c:v:{video_idx}', 'mjpeg', f'-disposition:v:{video_idx}', 'attached_pic'])
    
    # Add metadata tags
    if info['type'] == 'tv':
        cmd.extend([
            '-metadata', f"title={info['episode_title']}",
            '-metadata', f"show={info['show']}",
            '-metadata', f"season_number={info['season']}",
            '-metadata', f"episode_id=S{info['season']:02d}E{info['episode']:02d}",
            '-metadata', f"episode_sort={info['episode']}"
        ])
        if info.get('year'):
            cmd.extend(['-metadata', f"date={info['year']}"])
        if 'overview' in info:
            cmd.extend(['-metadata', f"description={info['overview']}"])
    elif info['type'] == 'movie':
        cmd.extend([
            '-metadata', f"title={info['title']}",
            '-metadata', f"date={info['year']}"
        ])
    
    cmd.append(output_path)
    
    if not verbose:
        cmd.extend(['-v', 'quiet', '-stats'])
    
    log(f"Running: {' '.join(cmd)}", verbose)
    result = subprocess.run(cmd)
    
    # Cleanup temp image
    if image_data and os.path.exists('/tmp/tvdb_poster.jpg'):
        os.remove('/tmp/tvdb_poster.jpg')
    
    return result.returncode == 0

def get_unique_output_path(output_path, new_file_path=None, verbose=False):
    """Get unique output path, checking for duplicates before appending number."""
    if not os.path.exists(output_path):
        return output_path
    
    # If we have a new file to compare, check if it's a duplicate
    if new_file_path and os.path.exists(new_file_path):
        existing_hash = partial_hash(output_path)
        new_hash = partial_hash(new_file_path)
        
        if existing_hash and new_hash and existing_hash == new_hash:
            log(f"Duplicate detected: {output_path} is identical to new file", verbose, force=True)
            # Delete the new file and return None to signal duplicate
            try:
                os.remove(new_file_path)
                log(f"Deleted duplicate file: {new_file_path}", verbose, force=True)
            except Exception as e:
                log(f"Failed to delete duplicate: {e}", verbose, force=True)
            return None
    
    # Not a duplicate, find unique name
    base_dir = os.path.dirname(output_path)
    stem = Path(output_path).stem
    ext = Path(output_path).suffix
    
    counter = 1
    while True:
        new_path = os.path.join(base_dir, f"{stem} ({counter}){ext}")
        if not os.path.exists(new_path):
            return new_path
        counter += 1

def reencode_file(mkv_path, output_dir, reason, info=None, verbose=False):
    """Re-encode file using HandBrake CLI with H.264 preset."""
    temp_dir = os.path.join(output_dir, '.temp_reencoding')
    os.makedirs(temp_dir, exist_ok=True)
    
    # Output to MKV with same base name
    temp_output = os.path.join(temp_dir, Path(mkv_path).stem + '.mkv')
    
    log(f"Re-encoding required ({reason}) - this will take time...", verbose, force=True)
    
    # Probe to get audio, subtitle, and video resolution information
    probe_data = probe_file(mkv_path)
    if not probe_data:
        log("Failed to probe file for track information", verbose, force=True)
        return None
    
    # Detect video resolution and frame rate to select appropriate preset
    video_height = None
    frame_rate = None
    for stream in probe_data.get('streams', []):
        if stream.get('codec_type') == 'video':
            video_height = stream.get('height')
            # Parse frame rate (format: "24000/1001" or "60")
            if stream.get('r_frame_rate'):
                fps_parts = stream['r_frame_rate'].split('/')
                if len(fps_parts) == 2:
                    frame_rate = float(fps_parts[0]) / float(fps_parts[1])
                else:
                    frame_rate = float(fps_parts[0])
            break
    
    # Determine if high frame rate (50/60fps)
    is_high_fps = frame_rate and frame_rate >= 50
    
    # Select HandBrake preset based on resolution and frame rate (capped at 1080p)
    if video_height:
        if video_height <= 480:
            preset = 'H.264 MKV 480p30'
            log(f"Detected {video_height}p @ {frame_rate:.2f}fps, using H.264 MKV 480p30 preset", verbose, force=True)
        elif video_height <= 576:
            preset = 'H.264 MKV 576p25'
            log(f"Detected {video_height}p @ {frame_rate:.2f}fps, using H.264 MKV 576p25 preset", verbose, force=True)
        elif video_height <= 720:
            preset = 'H.264 MKV 720p30'
            log(f"Detected {video_height}p @ {frame_rate:.2f}fps, using H.264 MKV 720p30 preset", verbose, force=True)
        else:
            # Cap at 1080p for all higher resolutions
            preset = 'H.264 MKV 1080p30'
            log(f"Detected {video_height}p @ {frame_rate:.2f}fps, using H.264 MKV 1080p30 preset (capped at 1080p)", verbose, force=True)
    else:
        preset = 'H.264 MKV 1080p30'
        log("Could not detect resolution, defaulting to H.264 MKV 1080p30 preset", verbose, force=True)
    
    # Collect all audio and subtitle track indices (HandBrake uses per-type indexing starting from 1)
    audio_track_nums = []
    subtitle_track_nums = []
    
    audio_count = 0
    subtitle_count = 0
    
    for stream in probe_data.get('streams', []):
        stream_type = stream.get('codec_type')
        lang = stream.get('tags', {}).get('language', 'und')
        
        if stream_type == 'audio':
            audio_count += 1
            audio_track_nums.append(str(audio_count))
        elif stream_type == 'subtitle':
            subtitle_count += 1
            if lang in ['eng', 'swe']:
                subtitle_track_nums.append(str(subtitle_count))
    
    # Build HandBrake command
    cmd = ['HandBrakeCLI', '-i', mkv_path, '-o', temp_output]
    cmd.extend(['--preset', preset])
    
    # Add all audio tracks
    if audio_track_nums:
        cmd.extend(['--audio', ','.join(audio_track_nums)])
        cmd.extend(['--aencoder', ','.join(['copy'] * len(audio_track_nums))])
    
    # Add English/Swedish subtitles
    if subtitle_track_nums:
        cmd.extend(['--subtitle', ','.join(subtitle_track_nums)])
    
    log(f"Running: {' '.join(cmd)}", verbose, force=True)
    
    # Always show HandBrake progress (it outputs to stderr)
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        return temp_output
    else:
        # Cleanup on failure
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return None

def process_file(mkv_path, output_dir, verbose=False, force_process=False, content_type='auto'):
    """Process a single MKV file."""
    log(f"\nProcessing: {mkv_path}", verbose, force=True)
    
    # Probe file first to check codec
    probe_data = probe_file(mkv_path)
    if not probe_data:
        return False, "Failed to probe file"
    
    # Check if re-encoding is needed
    needs_reencode = False
    reencode_reason = None
    video_codec = None
    
    # Check for DARKFLiX
    if 'darkflix' in mkv_path.lower():
        needs_reencode = True
        reencode_reason = "DARKFLiX"
    
    # Check if video codec is NOT H.264
    if not needs_reencode:
        for stream in probe_data.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_codec = stream.get('codec_name')
                if video_codec and video_codec != APPLE_TV_VIDEO_CODEC:
                    needs_reencode = True
                    reencode_reason = video_codec.upper()
                    break
    
    # Defer all re-encode files to second pass unless forced
    if needs_reencode and not force_process:
        log(f"{reencode_reason} detected - deferring to end of queue", verbose, force=True)
        return False, f"{reencode_reason} deferred"
    
    # Extract metadata from file early (needed for re-encoding)
    file_metadata = extract_file_metadata(mkv_path)
    log(f"File metadata: {file_metadata}", verbose)
    
    # Parse filename
    info = parse_filename(mkv_path)
    image_data = None
    
    # Merge file metadata with parsed info
    if not info.get('year') and file_metadata.get('year'):
        info['year'] = file_metadata['year']
        log(f"Using year from file metadata: {info['year']}", verbose)
    
    # Override content type if specified
    if content_type != 'auto':
        info['type'] = content_type
    
    # Fetch metadata from APIs before re-encoding
    if info['type'] == 'tv':
        year_display = info['year'] if info['year'] else 'Unknown'
        log(f"TV Show: {info['show']} ({year_display}) - S{info['season']:02d}E{info['episode']:02d} - {info['episode_title']}", verbose, force=True)
        
        # Fetch metadata from TVDB
        token = get_tvdb_token()
        if token:
            log("Fetching metadata from TVDB...", verbose, force=True)
            
            series_id = search_tvdb_series(info['show'], token)
            
            if not series_id and file_metadata.get('title') and file_metadata['title'] != info['show']:
                log(f"Trying TVDB search with metadata title: {file_metadata['title']}", verbose, force=True)
                series_id = search_tvdb_series(file_metadata['title'], token)
            
            if series_id:
                episode_data = get_tvdb_episode(series_id, info['season'], info['episode'], token)
                if episode_data:
                    if episode_data.get('name'):
                        info['episode_title'] = episode_data['name']
                    if episode_data.get('overview'):
                        info['overview'] = episode_data['overview']
                    if not info['year'] and episode_data.get('aired'):
                        info['year'] = episode_data['aired'][:4]
                
                artwork_url = get_tvdb_series_artwork(series_id, token)
                if artwork_url:
                    if not artwork_url.startswith('http'):
                        artwork_url = f"https://artworks.thetvdb.com{artwork_url}"
                    image_data = download_image(artwork_url, token)
                    if image_data:
                        log("Downloaded series artwork", verbose, force=True)
    elif info['type'] == 'movie':
        year_display = info['year'] if info['year'] else 'Unknown'
        log(f"Movie: {info['title']} ({year_display})", verbose, force=True)
        
        if TMDB_ACCESS_TOKEN:
            log("Fetching metadata from TMDB...", verbose, force=True)
            
            movie_id = search_tmdb_movie(info['title'], info['year'])
            
            if not movie_id and file_metadata.get('title') and file_metadata['title'] != info['title']:
                log(f"Trying TMDB search with metadata title: {file_metadata['title']}", verbose, force=True)
                movie_id = search_tmdb_movie(file_metadata['title'], info['year'])
            
            if movie_id:
                movie_data = get_tmdb_movie_details(movie_id)
                if movie_data:
                    if movie_data.get('title'):
                        info['title'] = movie_data['title']
                    if movie_data.get('overview'):
                        info['overview'] = movie_data['overview']
                    if not info['year'] and movie_data.get('release_date'):
                        info['year'] = movie_data['release_date'][:4]
                    
                    if movie_data.get('poster_path'):
                        image_data = download_tmdb_image(movie_data['poster_path'])
                        if image_data:
                            log("Downloaded movie poster", verbose, force=True)
    
    # Now perform re-encoding with metadata if needed
    temp_file = None
    if needs_reencode:
        log(f"{reencode_reason} detected - re-encoding required", verbose, force=True)
        temp_file = reencode_file(mkv_path, output_dir, reencode_reason, info, verbose)
        if not temp_file:
            return False, "Re-encoding failed"
        processing_path = temp_file
        # Re-probe the re-encoded file
        probe_data = probe_file(processing_path)
        if not probe_data:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            return False, "Failed to probe re-encoded file"
    else:
        processing_path = mkv_path
    
    # Build output path
    if info['type'] == 'tv':
        # Use year or omit for folder name
        if info['year']:
            show_dir = os.path.join(output_dir, f"{info['show']} ({info['year']})")
        else:
            show_dir = os.path.join(output_dir, info['show'])
        season_dir = os.path.join(show_dir, f"Season {info['season']}")
        os.makedirs(season_dir, exist_ok=True)
        output_name = f"{info['show']} S{info['season']:02d}E{info['episode']:02d} {info['episode_title']}.mp4"
        output_path = os.path.join(season_dir, output_name)
    elif info['type'] == 'movie':
        # Create Jellyfin-compatible folder structure
        if info['year']:
            movie_dir = os.path.join(output_dir, f"{info['title']} ({info['year']})")
            output_name = f"{info['title']} ({info['year']}).mp4"
        else:
            movie_dir = os.path.join(output_dir, info['title'])
            output_name = f"{info['title']}.mp4"
        
        os.makedirs(movie_dir, exist_ok=True)
        output_path = os.path.join(movie_dir, output_name)
        output_path = get_unique_output_path(output_path)
    else:
        output_name = Path(mkv_path).stem + '.mp4'
        output_path = os.path.join(output_dir, output_name)
        output_path = get_unique_output_path(output_path)
    
    compatible, incompatible = check_compatibility(probe_data)
    
    if incompatible:
        reasons = [f"{t} ({c})" for t, c in incompatible]
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)
        return False, f"Incompatible codecs: {', '.join(reasons)}"
    
    if not compatible:
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)
        return False, "No compatible streams found"
    
    selected_indices = display_tracks(compatible)
    if selected_indices is None:
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)
        return False, "User skipped"
    
    selected_streams = [compatible[i] for i in selected_indices]
    
    log(f"Extracting to: {output_path}", verbose, force=True)
    success = extract_streams(processing_path, output_path, selected_streams, info, image_data, verbose)
    
    # After successful extraction, check if final file has subtitles and update metadata if needed
    if success and os.path.exists(output_path) and info['type'] == 'tv':
        final_probe = probe_file(output_path)
        if final_probe:
            has_subs = False
            for stream in final_probe.get('streams', []):
                if stream.get('codec_type') == 'subtitle':
                    has_subs = True
                    break
            
            # If no subtitles in final file, prepend "(No Subs)" to episode title
            if not has_subs and not info['episode_title'].startswith('(No Subs)'):
                info['episode_title'] = f"(No Subs) {info['episode_title']}"
                # Rename file to include (No Subs) in filename
                old_path = output_path
                season_dir = os.path.dirname(output_path)
                output_name = f"{info['show']} S{info['season']:02d}E{info['episode']:02d} {info['episode_title']}.mp4"
                output_path = os.path.join(season_dir, output_name)
                if old_path != output_path:
                    os.rename(old_path, output_path)
                    log(f"Renamed to include (No Subs): {output_path}", verbose, force=True)
    
    # Cleanup temp file
    if temp_file and os.path.exists(temp_file):
        os.remove(temp_file)
        # Also cleanup temp directory if empty
        temp_dir = os.path.dirname(temp_file)
        if os.path.exists(temp_dir) and not os.listdir(temp_dir):
            os.rmdir(temp_dir)
    
    if success:
        return True, output_path
    else:
        return False, "Extraction failed"

def collect_files(inputs):
    """Collect video files from inputs (files or directories)."""
    files = []
    darkflix_files = []
    
    for input_path in inputs:
        path = Path(input_path)
        if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_FORMATS:
            if 'darkflix' in str(path).lower():
                darkflix_files.append(str(path))
            else:
                files.append(str(path))
        elif path.is_dir():
            for ext in SUPPORTED_VIDEO_FORMATS:
                # Check both lowercase and uppercase extensions
                for f in path.rglob(f'*{ext}'):
                    if 'darkflix' in str(f).lower():
                        darkflix_files.append(str(f))
                    else:
                        files.append(str(f))
                for f in path.rglob(f'*{ext.upper()}'):
                    if 'darkflix' in str(f).lower():
                        darkflix_files.append(str(f))
                    else:
                        files.append(str(f))
    
    # Remove duplicates and sort both lists alphabetically
    files = sorted(set(files))
    darkflix_files = sorted(set(darkflix_files))
    
    # Put darkflix files at the end
    return files + darkflix_files

def main():
    parser = argparse.ArgumentParser(description='Convert video files to MP4 (Apple TV compatible, H.264)')
    parser.add_argument('inputs', nargs='+', help='Video file(s) or directory containing video files (supports: MKV, MP4, AVI, WMV, FLV, MOV, M4V, TS, WebM, MPG, MPEG)')
    parser.add_argument('-o', '--output', required=True, help='Output directory for MP4 files')
    parser.add_argument('-t', '--type', choices=['tv', 'movie', 'auto'], default='auto', help='Content type (default: auto-detect)')
    parser.add_argument('-j', '--workers', type=int, default=1, help='Number of parallel workers (default: 1, max: number of CPU cores)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Check if HandBrakeCLI is available
    if not check_handbrake_cli():
        print("ERROR: HandBrakeCLI is not installed or not in PATH.")
        print("\nTo install HandBrake CLI:")
        print("  Ubuntu/Debian: sudo apt install handbrake-cli")
        print("  macOS: brew install handbrake")
        print("  Or download from: https://handbrake.fr/downloads.php")
        return 1
    
    # Validate workers argument
    max_workers = multiprocessing.cpu_count()
    if args.workers < 1:
        args.workers = 1
    elif args.workers > max_workers:
        print(f"Warning: Requested {args.workers} workers, but only {max_workers} CPU cores available. Using {max_workers} workers.")
        args.workers = max_workers
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    mkv_files = collect_files(args.inputs)
    
    if not mkv_files:
        print("No MKV or MP4 files found.")
        return 1
    
    print(f"Found {len(mkv_files)} video file(s)")
    if args.workers > 1:
        print(f"Using {args.workers} parallel workers")
    
    results = {'success': [], 'failed': [], 'deferred': []}
    
    # First pass: process non-H.265 files
    if args.workers == 1:
        # Sequential processing
        for mkv_file in mkv_files:
            success, message = process_file(mkv_file, str(output_dir), args.verbose, False, args.type)
            if message and "deferred" in message:
                results['deferred'].append(mkv_file)
            elif success:
                results['success'].append((mkv_file, message))  # message is output_path
            else:
                results['failed'].append((mkv_file, message))
    else:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_file = {
                executor.submit(process_file, mkv_file, str(output_dir), args.verbose, False, args.type): mkv_file
                for mkv_file in mkv_files
            }
            
            for future in as_completed(future_to_file):
                mkv_file = future_to_file[future]
                try:
                    success, message = future.result()
                    if message and "deferred" in message:
                        results['deferred'].append(mkv_file)
                    elif success:
                        results['success'].append((mkv_file, message))  # message is output_path
                    else:
                        results['failed'].append((mkv_file, message))
                except Exception as e:
                    results['failed'].append((mkv_file, f"Exception: {str(e)}"))
    
    # Second pass: process deferred files that need re-encoding
    if results['deferred']:
        print(f"\n{'='*60}")
        print(f"Processing {len(results['deferred'])} deferred file(s) that require re-encoding...")
        print(f"{'='*60}")
        
        if args.workers == 1:
            # Sequential processing
            for mkv_file in results['deferred']:
                success, message = process_file(mkv_file, str(output_dir), args.verbose, True, args.type)
                if success:
                    results['success'].append((mkv_file, message))  # message is output_path
                else:
                    results['failed'].append((mkv_file, message))
        else:
            # Parallel processing
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                future_to_file = {
                    executor.submit(process_file, mkv_file, str(output_dir), args.verbose, True, args.type): mkv_file
                    for mkv_file in results['deferred']
                }
                
                for future in as_completed(future_to_file):
                    mkv_file = future_to_file[future]
                    try:
                        success, message = future.result()
                        if success:
                            results['success'].append((mkv_file, message))  # message is output_path
                        else:
                            results['failed'].append((mkv_file, message))
                    except Exception as e:
                        results['failed'].append((mkv_file, f"Exception: {str(e)}"))
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Successful: {len(results['success'])}")
    print(f"Failed: {len(results['failed'])}")
    
    if results['success']:
        print("\nSuccessful conversions:")
        for source, output in results['success']:
            print(f"  {source} → {output}")
    
    if results['failed']:
        print("\nFailed files:")
        for file, reason in results['failed']:
            print(f"  - {file}: {reason}")
    
    return 0 if not results['failed'] else 1

if __name__ == '__main__':
    sys.exit(main())
