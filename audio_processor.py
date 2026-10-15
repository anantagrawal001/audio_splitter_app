import os
import subprocess
import json
import math
from pathlib import Path
from typing import List, Dict, Any

AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg', '.wma', '.opus', '.m4b'}

def get_audio_duration(file_path: str) -> float:
    """Uses ffprobe to get exact duration of audio file in seconds."""
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        file_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', check=True)
        data = json.loads(result.stdout)
        
        if 'format' in data and 'duration' in data['format']:
            return float(data['format']['duration'])
        
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'audio' and 'duration' in stream:
                return float(stream['duration'])
    except Exception as e:
        print(f"Error probing {file_path}: {e}")
    return 0.0


def scan_folder(folder_path: str) -> List[Dict[str, Any]]:
    """Scans directory for audio files and calculates split metadata."""
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Directory '{folder_path}' does not exist or is not a directory.")
    
    files = sorted([f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS])
    
    analysis = []
    chunk_limit_sec = 30 * 60  # 30 minutes limit threshold
    slice_length_sec = 29 * 60  # 29 minutes per slice
    
    for idx, file in enumerate(files, start=1):
        duration = get_audio_duration(str(file))
        needs_split = duration > chunk_limit_sec
        
        if needs_split:
            num_parts = math.ceil(duration / slice_length_sec)
        else:
            num_parts = 1
            
        parts = []
        for p in range(1, num_parts + 1):
            start_time = (p - 1) * slice_length_sec
            end_time = min(p * slice_length_sec, duration)
            parts.append({
                "part_num": p,
                "start_sec": start_time,
                "end_sec": end_time,
                "duration_sec": end_time - start_time,
                "new_filename": f"{idx:02d}_{p:02d}_{file.name}"
            })
            
        analysis.append({
            "video_seq": idx,
            "original_filename": file.name,
            "full_path": str(file),
            "duration_sec": duration,
            "duration_formatted": format_time(duration),
            "needs_split": needs_split,
            "total_parts": num_parts,
            "parts": parts
        })
        
    return analysis

def format_time(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"

def process_audio_file(file_info: Dict[str, Any], output_folder: str, progress_callback=None) -> List[str]:
    """Splits and renames audio chunks into output_folder using ffmpeg."""
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    created_files = []
    src_path = file_info["full_path"]
    
    for part in file_info["parts"]:
        out_filename = part["new_filename"]
        out_path = out_dir / out_filename
        
        if not file_info["needs_split"]:
            cmd = [
                'ffmpeg', '-y',
                '-i', src_path,
                '-c', 'copy',
                str(out_path)
            ]
        else:
            start_sec = part["start_sec"]
            dur_sec = part["duration_sec"]
            cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_sec),
                '-i', src_path,
                '-t', str(dur_sec),
                '-c', 'copy',
                str(out_path)
            ]
            
        try:
            subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', check=True)
        except subprocess.CalledProcessError:
            fallback_cmd = [
                'ffmpeg', '-y',
                '-ss', str(part["start_sec"]),
                '-i', src_path,
                '-t', str(part["duration_sec"]),
                str(out_path)
            ]
            subprocess.run(fallback_cmd, capture_output=True, encoding='utf-8', errors='replace', check=True)

            
        created_files.append(str(out_path))
        if progress_callback:
            progress_callback(out_filename)
            
    return created_files
