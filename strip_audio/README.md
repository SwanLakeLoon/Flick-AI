# Strip Audio Tool

A utility to recursively process video files in a directory and remove their audio tracks without re-encoding the video.

## Prerequisites

This tool requires `ffmpeg` to be installed and available on your system `PATH`.

- **macOS (Homebrew):** `brew install ffmpeg`
- **Ubuntu/Debian:** `sudo apt install ffmpeg`

## Usage

```bash
python strip_audio.py <input_folder> [options]
```

By default, the script scans the given folder for common video files (`.mp4`, `.mov`, etc.), explicitely avoids hidden and dotfiles, removes the audio, and **overwrites the original file** while preserving its creation metadata.

### Options

- `--mode {inplace,suffix,outdir}`
  - `inplace` (default): Overwrites the original file securely.
  - `suffix`: Creates a new file alongside the original (e.g. `video_noaudio.mp4`).
  - `outdir`: Mirrors the original directory structure into a new folder.
- `--output-dir PATH`: The destination directory (required if `--mode outdir`).
- `--dry-run`: Prints out the `ffmpeg` commands that would be run, without actually doing it.
- `--verbose`: Prints standard `ffmpeg` output for each file.
- `--extensions .mp4 .mov ...`: Override the default video extensions.

## Examples

**1. See what happens without changing anything:**

```bash
python strip_audio.py /path/to/my/videos --dry-run
```

**2. Safely create new files instead of overwriting:**

```bash
python strip_audio.py /path/to/my/videos --mode suffix
```

**3. Move all output to a new folder:**

```bash
python strip_audio.py /path/to/my/videos --mode outdir --output-dir /var/tmp/silent_videos
```
