# Video to MP4 Converter

Convert video files from various formats to MP4 with H.264 encoding, ensuring Apple TV compatibility. Automatically fetches metadata and artwork from TheTVDB (for TV shows) and TheMovieDB (for movies), organizing files in Jellyfin-compatible structure.

## Quick Start

```bash
# First time setup
cd mkv-to-mp4
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure API keys (edit .env file)
cp .env.example .env
# Add your TVDB_API_KEY, TMDB_API_KEY, and TMDB_ACCESS_TOKEN

# Subsequent usage
cd mkv-to-mp4
source venv/bin/activate

# Basic usage
./extract.py /path/to/input -o /path/to/output

# With parallel processing
./extract.py /path/to/input -o /path/to/output --workers 4

# Force content type
./extract.py /path/to/input -o /path/to/output --type tv|movie|auto
```

**Key Points:**
- Supports: MKV, MP4, AVI, WMV, FLV, MOV, M4V, TS, WebM, MPG, MPEG
- Default: Sequential processing (1 worker), auto-detect content type
- TV shows → TVDB metadata, organized as `Show (Year)/Season N/Show SxxExx Title.mp4`
- Movies → TMDB metadata, organized as `Movie (Year)/Movie (Year).mp4`
- Non-H.264 codecs are automatically re-encoded to H.264 (preserving quality)
- All video + all audio + English/Swedish subtitles selected automatically

## Features

- **Broad format support**: Accepts MKV, MP4, AVI, WMV, FLV, MOV, M4V, TS, WebM, MPG, MPEG
- **No re-encoding by default**: H.264 streams are copied directly (remux only) for fast processing
- **Smart re-encoding with HandBrake**: Automatically re-encodes non-H.264 codecs (H.265, VP9, MPEG-2, etc.) to H.264 using HandBrake CLI
- **Resolution-aware encoding**: Automatically selects appropriate HandBrake preset (480p/576p/720p/1080p) based on source resolution, capped at 1080p
- **Frame rate detection**: Uses 60fps presets for high frame rate content (≥50fps), 30fps presets for standard content (currently only 1080p and below supported)
- **Quality preservation**: HandBrake presets maintain source resolution and frame rate without unnecessary upscaling
- **Apple TV compatibility**: Outputs H.264 video with AAC/AC-3/E-AC-3 audio
- **Auto-track selection**: Automatically selects all video, all audio, and English/Swedish subtitles
- **Dual metadata sources**: 
  - TVDB for TV shows (episode info, descriptions, series posters)
  - TMDB for movies (title, year, overview, movie posters)
- **Auto-detection**: Automatically detects TV shows vs movies from filename
- **Jellyfin-ready**: Organizes content in Jellyfin-compatible folder structure
- **Batch processing**: Recursively processes entire directories
- **Alphabetical processing**: Files processed in order, with re-encode files deferred to end
- **No overwrites**: Appends numbers to filenames if file already exists
- **Subtitle conversion**: Converts SRT subtitles to mov_text for MP4 compatibility

## Requirements

- Python 3.6+
- ffmpeg (with ffprobe) - [ffmpeg.org](https://ffmpeg.org)
- HandBrake CLI - [handbrake.fr](https://handbrake.fr/downloads.php)
- TheTVDB API key (free at [thetvdb.com](https://thetvdb.com/api-information))
- TheMovieDB API key and access token (free at [themoviedb.org](https://www.themoviedb.org/settings/api))

## Installation

1. Clone or download this repository
2. Install HandBrake CLI:
```bash
# Ubuntu/Debian
sudo apt install handbrake-cli

# macOS
brew install handbrake

# Or download from: https://handbrake.fr/downloads.php
```

3. Create virtual environment and install dependencies:
```bash
cd mkv-to-mp4
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

4. Copy `.env.example` to `.env` and add your API keys:
```bash
cp .env.example .env
# Edit .env and add your API keys:
# - TVDB_API_KEY: Get from https://thetvdb.com/api-information
# - TMDB_API_KEY: Get from https://www.themoviedb.org/settings/api
# - TMDB_ACCESS_TOKEN: Get from https://www.themoviedb.org/settings/api (v4 Read Access Token)
```

## Usage

Always activate the virtual environment first:
```bash
source venv/bin/activate
```

### Process a directory (recommended)
```bash
./extract.py /path/to/video/files -o /path/to/output
```

### Process specific files
```bash
./extract.py file1.mkv file2.mkv -o /path/to/output
```

### Force content type (override auto-detection)
```bash
# Force TV mode
./extract.py /path/to/files -o /path/to/output --type tv

# Force movie mode
./extract.py /path/to/files -o /path/to/output --type movie
```

### Parallel processing (use multiple CPU cores)
```bash
# Use 4 workers (4 CPU cores)
./extract.py /path/to/files -o /path/to/output --workers 4

# Use all available CPU cores
./extract.py /path/to/files -o /path/to/output --workers $(nproc)
```

### Verbose mode (see detailed ffmpeg output)
```bash
./extract.py /path/to/files -o /path/to/output -v
```

## Output Structure

### TV Shows (Jellyfin format)
```
output/
└── Show Name (2021)/
    └── Season 3/
        └── Show Name S03E04 Episode Title.mp4
```

If year is not found in filename or TVDB:
```
output/
└── Show Name/
    └── Season 3/
        └── Show Name S03E04 Episode Title.mp4
```

### Movies (Jellyfin format)
```
output/
└── The Matrix (1999)/
    └── The Matrix (1999).mp4
```

If year is not found:
```
output/
└── Movie Title/
    └── Movie Title.mp4
```

## Content Type Detection

The script automatically detects content type from filename:
- **TV Shows**: Files with `SXXEXX` pattern (e.g., `Show.S01E01.mkv`)
- **Movies**: Files with year but no season/episode (e.g., `Movie.2021.mkv`)

You can override auto-detection with `--type tv` or `--type movie`.

## Processing Order

1. **H.264 files**: Processed first in alphabetical order with fast stream copy
2. **Non-H.264 and DARKFLiX files**: Deferred to end, then re-encoded in alphabetical order using HandBrake

## Summary Output

The script provides detailed summary output showing:
- **Successful conversions**: Source file path → Output file path
- **Failed files**: File path and reason for failure

Example:
```
============================================================
SUMMARY
============================================================
Successful: 2
Failed: 0

Successful conversions:
  /path/to/source/Show.S01E01.mkv → /output/Show (2021)/Season 1/Show S01E01 Episode Title.mp4
  /path/to/source/Movie.2020.mkv → /output/Movie (2020)/Movie (2020).mp4
```

## Re-encoding

The script automatically re-encodes files with non-H.264 video codecs using HandBrake CLI:
- **H.265/HEVC, VP9, MPEG-2, MPEG-4, etc.**: Re-encoded to H.264 for maximum compatibility
- **DARKFLiX releases**: Known to have compatibility issues, re-encoded automatically
- **Resolution-aware**: Automatically selects HandBrake preset based on source resolution:
  - 480p or lower → `H.264 MKV 480p30`
  - 576p → `H.264 MKV 576p25`
  - 720p → `H.264 MKV 720p30` or `720p60` (for high FPS)
  - 1080p or higher → `H.264 MKV 1080p30` (capped at 1080p)
- **Frame rate detection**: Uses 60fps presets for content ≥50fps, 30fps presets for standard content (currently only 1080p and below supported)
- **Quality preservation**: Preserves source resolution and frame rate without upscaling
- **Audio/subtitles**: All audio tracks copied without re-encoding, English/Swedish subtitles included
- **Metadata**: TV show and movie metadata embedded during re-encoding

Re-encoding workflow:
1. HandBrake re-encodes video to H.264 in MKV container with metadata
2. ffmpeg remuxes MKV to MP4 and embeds artwork (poster/cover art)
3. Final MP4 is Apple TV compatible with full metadata

## Supported Input Formats

- **Containers**: MKV, MP4, AVI, WMV, FLV, MOV, M4V, TS, WebM, MPG, MPEG
- **Video codecs**: H.264 (copied), H.265/HEVC, VP9, MPEG-2, MPEG-4, and others (re-encoded to H.264)
- **Audio codecs**: AAC, AC-3, E-AC-3 (Dolby Digital Plus) - copied without re-encoding
- **Subtitles**: mov_text, SRT (converted to mov_text), SubRip, ASS, SSA (converted to mov_text)
  - **Note**: DVB subtitles are automatically excluded as they cannot be stored in MP4 containers

## Track Selection

The script automatically selects:
- ✓ All video tracks
- ✓ All audio tracks (any language)
- ✓ English and Swedish subtitles only (excluding dvb_subtitle which is incompatible with MP4)

**Note:** DVB subtitles (bitmap-based) cannot be stored in MP4 containers and are automatically excluded. Other subtitle formats (SRT, ASS, SSA) are converted to mov_text for MP4 compatibility.

Example output:
```
Available tracks:
[1] VIDEO: h264
[2] AUDIO: aac (eng) - English
[3] AUDIO: aac (spa) - Spanish
[4] SUBTITLE: dvb_subtitle (eng)
[5] SUBTITLE: ass (eng)

Auto-selected: 1, 2, 3, 5 (video + all audio + English/Swedish subs, excluding dvb_subtitle)
```

## Metadata

The script uses a multi-source approach to gather the best metadata:

1. **Extracts embedded metadata** from source file (title, year, artist/director)
2. **Parses filename** for show/movie name, season, episode, year
3. **Searches APIs** using both filename and embedded metadata
4. **Merges results** to create complete metadata

### TV Shows (from TVDB)
The script automatically:
- Fetches episode information (title, description, year)
- Downloads and embeds series poster artwork as cover art
- Adds metadata tags (title, show, season, episode, description, year)
- Uses embedded file metadata as fallback search term if filename search fails
- Falls back to filename parsing if TVDB fetch fails
- **Adds "(No Subs)" prefix** to episode title in metadata and filename if final MP4 has no subtitles

### Movies (from TMDB)
The script automatically:
- Fetches movie information (title, year, overview)
- Downloads and embeds movie poster artwork as cover art
- Adds metadata tags (title, year, overview)
- Uses embedded file metadata as fallback search term if filename search fails
- Falls back to filename parsing if TMDB fetch fails

**Example:** A file named `Movie.mkv` with embedded title "The Matrix" and year "1999" will:
1. Try TMDB search with "Movie"
2. If not found, try TMDB search with "The Matrix" (from metadata)
3. Use year "1999" from metadata for output folder structure

**No Subtitles Indicator:** For TV shows, if the final MP4 file contains no subtitles, "(No Subs)" is automatically prepended to the episode title in both the filename and embedded metadata. Example: `Show Name S01E01 (No Subs) Episode Title.mp4`

## File Naming

The script parses standard scene release formats:

**TV Shows:**
- `Show.Name.YYYY.SXXEXX.Title.1080p.WEB.h264-GROUP.mkv`
- `Show.Name.SXXEXX.Title.1080p.WEB.h264-GROUP.mkv`

**Movies:**
- `Movie.Name.YYYY.1080p.WEB.h264-GROUP.mkv`

**Output naming:**
- TV: `Show Name S03E04 Episode Title.mp4`
- Movies: `Movie Title (2021).mp4`

## Duplicate Handling

The script prevents duplicate files by checking if the output file already exists:
- **Unique naming**: If a file with the same name exists, appends (1), (2), etc.
- **No overwrites**: Existing files are never overwritten

Example behavior:
- First run: Creates `Show Name S03E04 Episode Title.mp4`
- Second run with different source: Creates `Show Name S03E04 Episode Title (1).mp4`

## Temporary Files

Re-encoded files are temporarily stored in `.temp_reencoding/` within the output directory and cleaned up automatically after successful processing. If the script crashes during re-encoding, you may need to manually delete this directory.

## Limitations

- **Frame rate**: 60fps presets currently only supported for 1080p and below
- **Maximum resolution**: Output is capped at 1080p (higher resolution sources are downscaled)
- **Subtitle formats**: DVB subtitles (bitmap-based) cannot be stored in MP4 containers and are automatically excluded
- **API dependencies**: Requires internet connection for metadata fetching from TVDB and TMDB

## Known Issues

- Some DARKFLiX releases may have corrupt reference frames (warning messages during re-encoding are normal)
- Very large files (>10GB) may require significant temporary disk space during re-encoding

## Troubleshooting

### Common Issues

**"HandBrakeCLI is not installed"**
- Install HandBrake CLI: `sudo apt install handbrake-cli` (Ubuntu/Debian) or `brew install handbrake` (macOS)
- Or download from: https://handbrake.fr/downloads.php

**"TVDB auth failed" or "TMDB search failed"**
- Verify your API keys are correct in `.env`
- Check that TMDB_ACCESS_TOKEN is the v4 Read Access Token (not the API key)
- Ensure you have internet connectivity

**Output directory is empty after processing**
- Check the summary output for error messages
- Run with `-v` flag for verbose output to see detailed ffmpeg logs
- Verify you have write permissions to the output directory

**File not found after "Successful" message**
- Check if the file was created in a subdirectory (TV shows use `Show (Year)/Season N/` structure)
- Look for files with "(No Subs)" prefix if no subtitles were found

### Performance

- **Re-encoding speed**: Approximately 30-35 fps on modern CPUs (Intel i5-6500 or better)
- **Remux-only speed**: Near-instant (1-2 seconds per file)
- **Disk space**: Re-encoding requires temporary space equal to output file size
- **Parallel processing**: Use `--workers` to process multiple files simultaneously (recommended: 2-4 workers)

## Examples

### Basic Usage

Process TV show directory:
```bash
./extract.py ~/Downloads/TV\ Shows -o ~/Media/TV
```

Process movie directory:
```bash
./extract.py ~/Downloads/Movies -o ~/Media/Movies --type movie
```

Process mixed content with auto-detection:
```bash
./extract.py ~/Downloads -o ~/Media
```

Process specific files:
```bash
./extract.py movie1.mkv movie2.mkv show.S01E01.mkv -o ~/Media
```

### Advanced Usage

Process with 4 parallel workers:
```bash
./extract.py ~/Downloads/TV\ Shows -o ~/Media/TV --workers 4
```

Process movies with maximum available workers:
```bash
./extract.py ~/Downloads/Movies -o ~/Media/Movies --type movie --workers $(nproc)
```

Process with verbose output to see ffmpeg details:
```bash
./extract.py ~/Downloads/TV\ Shows -o ~/Media/TV -v
```

Force TV mode for files without season/episode in filename:
```bash
./extract.py ~/Downloads/Specials -o ~/Media/TV --type tv
```

Combine multiple options:
```bash
./extract.py ~/Downloads -o ~/Media --workers 4 --type auto -v
```

### Real-world Scenarios

Batch process entire download folder with 4 workers:
```bash
cd ~/Github/mkv-to-mp4
source venv/bin/activate
./extract.py ~/Downloads/Complete -o ~/Media --workers 4
```

Process only movies from a mixed directory:
```bash
./extract.py ~/Downloads/2024 -o ~/Media/Movies --type movie --workers 2
```

Quick single file conversion:
```bash
./extract.py ~/Downloads/show.mkv -o ~/Media/TV
```

Process with maximum performance (all CPU cores):
```bash
./extract.py ~/Downloads/TV -o ~/Media/TV --workers $(nproc)
```

## Command Line Options

```
usage: extract.py [-h] -o OUTPUT [-t {tv,movie,auto}] [-j WORKERS] [-v] inputs [inputs ...]

positional arguments:
  inputs                Video file(s) or directory containing video files
                        Supported formats: MKV, MP4, AVI, WMV, FLV, MOV, M4V, TS, WebM, MPG, MPEG

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output directory for MP4 files
  -t {tv,movie,auto}, --type {tv,movie,auto}
                        Content type (default: auto-detect)
  -j WORKERS, --workers WORKERS
                        Number of parallel workers (default: 1, max: number of CPU cores)
  -v, --verbose         Verbose output
```
