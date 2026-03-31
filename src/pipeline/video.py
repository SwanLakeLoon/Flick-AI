"""
Flick AI — Video Utilities
============================
Frame extraction, video splitting, duration checking, and audio stripping.
"""

import os
import re
import subprocess
import glob
from pathlib import Path
from typing import Optional

from .config import EPHEMERAL_DIR, MAX_SEGMENT_SECONDS


def get_video_duration_seconds(video_path: str) -> float:
    """Return video duration in seconds using ffprobe, or 0 on failure."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def extract_frame_at_timestamp(video_path: str, timestamp_sec: float, output_path: str) -> Optional[str]:
    """Extract a single frame from a video at the exact timestamp using ffmpeg."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if os.path.exists(output_path):
        return output_path

    use_video_path = video_path

    # Handle the case where Gemini Flash returns a GLOBAL timestamp
    # for a split video segment.
    if "_splits" in video_path and "_seg" in video_path:
        filename = os.path.basename(video_path)
        splits_dir = os.path.dirname(video_path)
        base_dir = os.path.dirname(splits_dir)

        orig_name = re.sub(r'_seg\d+', '', filename)
        orig_path = os.path.join(base_dir, orig_name)

        match = re.search(r'_seg(\d+)', filename)
        if match and os.path.exists(orig_path):
            seg_idx = int(match.group(1))
            if timestamp_sec > 120.0 or (seg_idx * 120) <= timestamp_sec < ((seg_idx + 1) * 120 + 10):
                use_video_path = orig_path

    cmd = [
        "ffmpeg",
        "-ss", str(timestamp_sec),
        "-i", use_video_path,
        "-frames:v", "1",
        "-vf", "scale=3840:-2",
        "-q:v", "1",
        "-y",
        output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(output_path):
            return output_path
        return None
    except Exception as e:
        print(f"  [Frame extract error] Failed to extract {timestamp_sec}s from {os.path.basename(video_path)}: {e}")
        return None


def split_long_videos(videos: list[str], target_dir: str) -> list[str]:
    """
    Check each video's duration. If > MAX_SEGMENT_SECONDS, split it into
    ~2-minute segments using ffmpeg. Returns the (possibly expanded) list
    of video paths to process.
    """
    splits_dir = os.path.join(EPHEMERAL_DIR, "_splits")
    result_videos: list[str] = []

    for vid_path in videos:
        duration = get_video_duration_seconds(vid_path)
        vid_name = os.path.basename(vid_path)

        if duration <= MAX_SEGMENT_SECONDS:
            print(f"  [{vid_name}] {duration:.0f}s — under {MAX_SEGMENT_SECONDS}s, no split needed.")
            result_videos.append(vid_path)
            continue

        stem = Path(vid_name).stem
        ext = Path(vid_name).suffix
        existing_splits = sorted(glob.glob(os.path.join(splits_dir, f"{stem}_seg*{ext}")))
        if existing_splits:
            print(f"  [{vid_name}] {duration:.0f}s — found {len(existing_splits)} cached splits.")
            result_videos.extend(existing_splits)
            continue

        n_segments = int(duration // MAX_SEGMENT_SECONDS) + (1 if duration % MAX_SEGMENT_SECONDS else 0)
        print(f"  [{vid_name}] {duration:.0f}s — splitting into ~{n_segments} segments of {MAX_SEGMENT_SECONDS}s...")
        os.makedirs(splits_dir, exist_ok=True)

        out_pattern = os.path.join(splits_dir, f"{stem}_seg%03d{ext}")
        cmd = [
            "ffmpeg", "-i", vid_path,
            "-c", "copy",
            "-map", "0",
            "-segment_time", str(MAX_SEGMENT_SECONDS),
            "-f", "segment",
            "-reset_timestamps", "1",
            out_pattern
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True)
            new_splits = sorted(glob.glob(os.path.join(splits_dir, f"{stem}_seg*{ext}")))
            print(f"    → Created {len(new_splits)} segments.")
            result_videos.extend(new_splits)
        except Exception as e:
            print(f"    → Split failed: {e}. Using original file as fallback.")
            result_videos.append(vid_path)

    return result_videos


def strip_audio(video_path: str, output_path: Optional[str] = None) -> str:
    """Strip audio from a video file. Returns path to the stripped file."""
    if output_path is None:
        stem = Path(video_path).stem
        ext = Path(video_path).suffix
        output_path = os.path.join(EPHEMERAL_DIR, f"{stem}_noaudio{ext}")

    if os.path.exists(output_path):
        return output_path

    cmd = [
        "ffmpeg", "-i", video_path,
        "-an", "-c:v", "copy",
        "-y", output_path
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True)
        return output_path
    except Exception as e:
        print(f"  [Audio strip error] {os.path.basename(video_path)}: {e}")
        return video_path  # fallback to original
