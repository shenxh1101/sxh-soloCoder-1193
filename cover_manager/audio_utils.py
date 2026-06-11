"""音频工具 - ffmpeg 混音和音频信息获取"""
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


class FFmpegError(Exception):
    """FFmpeg 相关错误
    """
    pass


def check_ffmpeg() -> bool:
    """检查 ffmpeg 是否可用"""
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def get_audio_info(file_path: str) -> Tuple[float, int]:
    """
    获取音频文件信息（时长和文件大小
    返回 (duration_seconds, file_size_bytes)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    file_size = os.path.getsize(file_path)

    if not shutil.which("ffprobe"):
        return 0.0, file_size

    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return 0.0, file_size

        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0.0))
        return duration, file_size
    except (json.JSONDecodeError, ValueError, KeyError):
        return 0.0, file_size


def mix_audio(
    vocal_path: str,
    instrumental_path: str,
    output_path: str,
    vocal_gain: float = 0.0,
    instrumental_gain: float = 0.0,
    sample_rate: int = 44100,
) -> str:
    """
    使用 ffmpeg 混音（干声 + 伴奏
    返回输出文件路径
    """
    if not shutil.which("ffmpeg"):
        raise FFmpegError("未找到 ffmpeg，请先安装 ffmpeg 并添加到 PATH")

    if not os.path.exists(vocal_path):
        raise FileNotFoundError(f"干声文件不存在: {vocal_path}")

    if not os.path.exists(instrumental_path):
        raise FileNotFoundError(f"伴奏文件不存在: {instrumental_path}")

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    vocal_filter = f"[0:a]volume={vocal_gain}dB[a]" if vocal_gain != 0 else "[0:a]"
    instrumental_filter = f"[1:a]volume={instrumental_gain}dB[b]" if instrumental_gain != 0 else "[1:a]"
    filter_complex = f"{vocal_filter};{instrumental_filter};[a][b]amix=inputs=2:duration=longest"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", vocal_path,
        "-i", instrumental_path,
        "-filter_complex", filter_complex,
        "-ar", str(sample_rate),
        "-ac", "2",
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise FFmpegError(f"混音失败: {result.stderr}")
        return output_path
    except FileNotFoundError:
            raise FFmpegError("ffmpeg 命令执行失败，请确认 ffmpeg 已正确安装")


def generate_output_path(song_title: str, version: int, output_dir: str = "") -> str:
    """生成混音输出文件路径"""
    safe_chars = set(' -_')
    safe_title = "".join(c for c in song_title if c.isalnum() or c in safe_chars).strip()
    if not safe_title:
        safe_title = "mix"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_title}_v{version:03d}_{timestamp}.wav"
    if output_dir:
        return os.path.join(output_dir, filename)
    return filename


def format_duration(seconds: float) -> str:
    """格式化时长显示"""
    if seconds <= 0:
        return "0:00"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小显示"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
