"""
Google Drive ingestion module.

Downloads video files from a Drive folder, transcribes with Whisper,
extracts frames with ffmpeg. Returns the same artifact shape as ingest_youtube().
"""
import subprocess
import hashlib
from pathlib import Path

from stepwise.config import settings
from stepwise.ingestion._utils import dedup_frames

SUPPORTED_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",       # .mov
    "video/x-msvideo",       # .avi
    "video/webm",
    "video/x-matroska",      # .mkv
    "video/mpeg",
}

# Loom share URL pattern — treated like a URL-based source
LOOM_DOMAIN = "loom.com"


def _get_drive_service(token_path: Path):
    """Build an authenticated Drive service from a saved token."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(token_path))
    return build("drive", "v3", credentials=creds)


def list_drive_files(folder_id: str, token_path: Path, recursive: bool = False) -> list[dict]:
    """
    List all video files in a Drive folder.

    With recursive=True, descends into subfolders. Returns list of
    {id, name, mimeType, webViewLink, modifiedTime} dicts.
    """
    service = _get_drive_service(token_path)
    results: list[dict] = []
    _list_drive_files_recursive(service, folder_id, results, recursive)
    return results


def _list_drive_files_recursive(service, folder_id: str, results: list[dict], recursive: bool) -> None:
    page_token = None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType, webViewLink, modifiedTime, size)",
            pageToken=page_token,
            pageSize=100,
        ).execute()

        for f in resp.get("files", []):
            mime = f.get("mimeType", "")
            if mime == "application/vnd.google-apps.folder" and recursive:
                _list_drive_files_recursive(service, f["id"], results, recursive)
            elif mime in SUPPORTED_MIME_TYPES or _is_loom_shortcut(f):
                results.append(f)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def list_drive_changes(folder_id: str, token_path: Path, since: str, recursive: bool = False) -> list[dict]:
    """
    Return video files modified after `since` (ISO 8601 string, e.g. '2025-01-01T00:00:00Z').
    """
    all_files = list_drive_files(folder_id, token_path, recursive=recursive)
    return [f for f in all_files if (f.get("modifiedTime") or "") > since]


def _is_loom_shortcut(file_meta: dict) -> bool:
    """Check if a Drive file is a shortcut/link to a Loom video."""
    return LOOM_DOMAIN in file_meta.get("webViewLink", "")


def _stable_id(drive_file_id: str) -> str:
    """Generate a stable local ID from a Drive file ID."""
    return hashlib.sha1(drive_file_id.encode()).hexdigest()[:16]


def _download_drive_file(file_id: str, dest_path: Path, token_path: Path) -> None:
    """Download a Drive file to dest_path using the Drive API."""
    from googleapiclient.http import MediaIoBaseDownload

    service = _get_drive_service(token_path)
    request = service.files().get_media(fileId=file_id)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def _whisper_transcribe_file(video_path: Path, audio_dir: Path) -> list[dict]:
    """Transcribe a local video file using Whisper. Returns [{text, start, duration}]."""
    import whisper

    audio_path = audio_dir / "audio.mp3"
    if not audio_path.exists():
        subprocess.run(
            ["ffmpeg", "-i", str(video_path), "-vn", "-ar", "16000",
             "-ac", "1", "-b:a", "64k", str(audio_path), "-y"],
            check=True, capture_output=True,
        )

    from stepwise.ml.registry import get_whisper_model

    result = get_whisper_model().transcribe(str(audio_path), word_timestamps=False)

    return [
        {"text": seg["text"].strip(), "start": seg["start"],
         "duration": seg["end"] - seg["start"]}
        for seg in result["segments"]
    ]


def _extract_frames_from_file(video_path: Path, output_dir: Path, interval: int) -> list[dict]:
    """Extract frames from a local video file at `interval` seconds."""
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-i", str(video_path),
         "-vf", f"fps=1/{interval}", "-q:v", "2",
         str(frames_dir / "frame_%04d.jpg"), "-y"],
        check=True, capture_output=True,
    )

    frames = []
    for frame_file in sorted(frames_dir.glob("frame_*.jpg")):
        idx = int(frame_file.stem.split("_")[1])
        timestamp = (idx - 1) * interval
        frames.append({"path": str(frame_file), "timestamp": float(timestamp)})

    return dedup_frames(frames)


def ingest_drive_file(file_meta: dict, token_path: Path) -> dict:
    """
    Ingest a single Drive video file.
    Returns same shape as ingest_youtube():
    {video_id, title, url, transcript, frames}
    """
    file_id = file_meta["id"]
    name    = file_meta.get("name", file_id)
    url     = file_meta.get("webViewLink", f"drive://{file_id}")

    # Stable local ID derived from Drive file ID
    local_id = _stable_id(file_id)
    work_dir = settings.frames_dir / local_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # Determine extension
    ext = Path(name).suffix or ".mp4"
    video_path = work_dir / f"video{ext}"

    # Download if not already cached
    if not video_path.exists():
        _download_drive_file(file_id, video_path, token_path)

    transcript = _whisper_transcribe_file(video_path, work_dir)
    frames = _extract_frames_from_file(video_path, work_dir, settings.frame_interval_seconds)

    return {
        "video_id": local_id,
        "title": Path(name).stem,  # filename without extension
        "url": url,
        "transcript": transcript,
        "frames": frames,
    }


def ingest_loom_url(loom_url: str) -> dict:
    """
    Ingest a Loom video URL. Uses yt-dlp (which supports Loom) to download,
    then Whisper to transcribe and ffmpeg to extract frames.
    """
    local_id = _stable_id(loom_url)
    work_dir = settings.frames_dir / local_id
    work_dir.mkdir(parents=True, exist_ok=True)

    video_path = work_dir / "video.mp4"

    if not video_path.exists():
        subprocess.run(
            ["yt-dlp", "-f", "best[ext=mp4]/best", "-o", str(video_path), loom_url],
            check=True, capture_output=True,
        )

    # Try to get title from yt-dlp
    title_result = subprocess.run(
        ["yt-dlp", "--print", "title", "--no-download", loom_url],
        capture_output=True, text=True,
    )
    title = title_result.stdout.strip() or Path(loom_url).stem

    transcript = _whisper_transcribe_file(video_path, work_dir)
    frames = _extract_frames_from_file(video_path, work_dir, settings.frame_interval_seconds)

    return {
        "video_id": local_id,
        "title": title,
        "url": loom_url,
        "transcript": transcript,
        "frames": frames,
    }
