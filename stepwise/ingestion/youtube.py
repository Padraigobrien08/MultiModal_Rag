import subprocess
from pathlib import Path
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled
import re

from stepwise.config import settings
from stepwise.ingestion._utils import dedup_frames


def _extract_video_id(url: str) -> str:
    patterns = [
        r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:embed/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Cannot extract video ID from URL: {url}")


def _get_transcript(video_id: str) -> list[dict]:
    """Returns list of {text, start, duration} dicts. Falls back to Whisper if no captions."""
    try:
        return YouTubeTranscriptApi().fetch(video_id).to_raw_data()
    except (NoTranscriptFound, TranscriptsDisabled):
        return _whisper_transcribe(video_id)


def _whisper_transcribe(video_id: str) -> list[dict]:
    import whisper

    video_dir = settings.frames_dir / video_id
    audio_path = video_dir / "audio.mp3"
    video_dir.mkdir(parents=True, exist_ok=True)

    if not audio_path.exists():
        subprocess.run(
            ["yt-dlp", "-x", "--audio-format", "mp3", "-o", str(audio_path),
             f"https://www.youtube.com/watch?v={video_id}"],
            check=True, capture_output=True,
        )

    from stepwise.ml.registry import get_whisper_model

    result = get_whisper_model().transcribe(str(audio_path), word_timestamps=False)

    return [
        {"text": seg["text"].strip(), "start": seg["start"], "duration": seg["end"] - seg["start"]}
        for seg in result["segments"]
    ]


def _get_title(video_id: str) -> str:
    result = subprocess.run(
        ["yt-dlp", "--print", "title", "--no-download",
         f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True,
    )
    title = result.stdout.strip()
    return title if title else video_id


def _extract_frames(video_id: str, output_dir: Path, interval: int) -> list[dict]:
    """
    Downloads video with yt-dlp and extracts frames at `interval` seconds.
    Returns list of {path, timestamp} dicts.
    """
    video_dir = output_dir / video_id
    video_dir.mkdir(parents=True, exist_ok=True)

    video_path = video_dir / "video.mp4"
    if not video_path.exists():
        subprocess.run(
            [
                "yt-dlp",
                "-f", "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]",
                "--merge-output-format", "mp4",
                "-o", str(video_path),
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            check=True,
            capture_output=True,
        )

    frames_dir = video_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    subprocess.run(
        [
            "ffmpeg", "-i", str(video_path),
            "-vf", f"fps=1/{interval}",
            "-q:v", "2",
            str(frames_dir / "frame_%04d.jpg"),
            "-y",
        ],
        check=True,
        capture_output=True,
    )

    frames = []
    for frame_file in sorted(frames_dir.glob("frame_*.jpg")):
        idx = int(frame_file.stem.split("_")[1])
        timestamp = (idx - 1) * interval
        frames.append({"path": str(frame_file), "timestamp": float(timestamp)})

    return dedup_frames(frames)


def ingest_youtube(url: str) -> dict:
    """
    Ingest a YouTube URL. Returns raw artifacts:
    {video_id, transcript: [{text, start, duration}], frames: [{path, timestamp}]}
    """
    video_id = _extract_video_id(url)
    title = _get_title(video_id)
    transcript = _get_transcript(video_id)
    frames = _extract_frames(video_id, settings.frames_dir, settings.frame_interval_seconds)

    return {
        "video_id": video_id,
        "title": title,
        "url": url,
        "transcript": transcript,
        "frames": frames,
    }
