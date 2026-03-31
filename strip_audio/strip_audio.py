#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.wmv', '.flv', '.webm'}


def check_prerequisites():
    """Ensure ffmpeg is installed and available on PATH."""
    if shutil.which('ffmpeg') is None:
        print("Error: 'ffmpeg' is not installed or not found on PATH.", file=sys.stderr)
        print("Please install ffmpeg (e.g., 'brew install ffmpeg' or 'apt install ffmpeg') to use this tool.", file=sys.stderr)
        sys.exit(1)


def process_video(input_path: Path, output_path: Path, dry_run: bool, verbose: bool):
    """Run ffmpeg to copy streams minus audio."""
    # Ensure the output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        'ffmpeg',
        '-y',               # Overwrite output files without asking
        '-i', str(input_path),
        '-map', '0',        # Copy all streams
        '-map', '-0:a',     # Drop all audio streams
        '-c', 'copy',       # Use stream copy (no re-encoding)
        str(output_path)
    ]
    
    if dry_run:
        print(f"Would run: {' '.join(cmd)}")
        return True

    # Run ffmpeg
    try:
        if verbose:
            subprocess.run(cmd, check=True)
        else:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        # Try to restore timestamps
        try:
            st = os.stat(input_path)
            os.utime(output_path, (st.st_atime, st.st_mtime))
        except Exception as e:
            if verbose:
                print(f"Warning: Failed to preserve timestamps for {output_path}: {e}")
                
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error processing {input_path.name}: ffmpeg exited with code {e.returncode}")
        return False
    except FileNotFoundError:
        print("Error: ffmpeg not found when trying to process.", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Recursively remove audio tracks from videos in a folder.")
    parser.add_argument("input_folder", help="Folder containing the video files to process.")
    parser.add_argument("--mode", choices=['inplace', 'suffix', 'outdir'], default='inplace',
                        help="Output mode. 'inplace' (default) replaces the original file. "
                             "'suffix' creates a new file next to original. 'outdir' mirrors to a new directory.")
    parser.add_argument("--output-dir", type=Path, help="Required if --mode is 'outdir'.")
    parser.add_argument("--extensions", nargs='+', default=list(DEFAULT_EXTENSIONS),
                        help=f"File extensions to process (default: {' '.join(DEFAULT_EXTENSIONS)})")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be processed without running ffmpeg.")
    parser.add_argument("--verbose", action="store_true", help="Show ffmpeg output for each file.")
    
    args = parser.parse_args()
    
    check_prerequisites()
    
    input_folder = Path(args.input_folder).resolve()
    
    if not input_folder.is_dir():
        print(f"Error: {input_folder} is not a valid directory.")
        sys.exit(1)
        
    if args.mode == 'outdir' and not args.output_dir:
        print("Error: --output-dir is required when --mode is 'outdir'.", file=sys.stderr)
        sys.exit(1)
        
    outdir = args.output_dir.resolve() if args.output_dir else None
    
    extensions = {ext.lower() if ext.startswith('.') else f".{ext.lower()}" for ext in args.extensions}
    
    print(f"Searching for videos in {input_folder}...")
    
    videos_to_process = []
    for path in input_folder.rglob('*'):
        if not path.is_file():
            continue
        # Skip hidden files
        if path.name.startswith('.'):
            continue
        if path.suffix.lower() in extensions:
            videos_to_process.append(path)
            
    total_videos = len(videos_to_process)
    if total_videos == 0:
        print("No videos found matching the given extensions.")
        return
        
    print(f"Found {total_videos} videos to process.")
    
    processed_count = 0
    skipped_count = 0
    error_count = 0
    
    for i, input_path in enumerate(videos_to_process, 1):
        print(f"[{i}/{total_videos}] Processing {input_path.name}...")
        
        output_path = None
        temp_path = None
        
        if args.mode == 'inplace':
            # Write to a temp file, then rename
            temp_path = input_path.with_name(f".{input_path.name}.temp{input_path.suffix}")
            output_path = temp_path
        elif args.mode == 'suffix':
            output_path = input_path.with_name(f"{input_path.stem}_noaudio{input_path.suffix}")
        elif args.mode == 'outdir':
            rel_path = input_path.relative_to(input_folder)
            output_path = outdir / rel_path
            
        if not args.dry_run and args.mode == 'inplace':
           if temp_path.exists():
               temp_path.unlink()
               
        success = process_video(input_path, output_path, args.dry_run, args.verbose)
        
        if success:
            if not args.dry_run and args.mode == 'inplace':
                # Atomically replace the original
                temp_path.replace(input_path)
            processed_count += 1
        else:
            if not args.dry_run and args.mode == 'inplace' and temp_path.exists():
                temp_path.unlink()
            error_count += 1

    print("\nProcessing complete.")
    print(f"Total found: {total_videos}")
    print(f"Successfully processed: {processed_count}")
    print(f"Errors: {error_count}")


if __name__ == "__main__":
    main()
