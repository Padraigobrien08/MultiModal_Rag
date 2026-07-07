"""Translate raw ingestion exceptions into short, user-actionable messages.

Ingestion failures surface to non-technical users in the job detail view, so a
bare stack-trace string ("CalledProcessError ...") is unhelpful. `humanize_error`
maps the failures we actually see into a sentence that tells the user what to do.
Anything unrecognised falls back to the original message so nothing is hidden.
"""

from __future__ import annotations

import subprocess


def humanize_error(exc: Exception) -> str:
    raw = str(exc).strip()

    # Missing system tools (ffmpeg / yt-dlp not installed or not on PATH).
    if isinstance(exc, FileNotFoundError):
        missing = exc.filename or raw
        if missing and "ffmpeg" in str(missing):
            return "ffmpeg is not installed or not on PATH — install ffmpeg to extract frames."
        if missing and ("yt-dlp" in str(missing) or "yt_dlp" in str(missing)):
            return "yt-dlp is not installed or not on PATH — install yt-dlp to download videos."
        return f"A required tool was not found: {missing}"

    lowered = raw.lower()

    # Bad / unrecognised source URL (raised by _extract_video_id).
    if "cannot extract video id" in lowered or "invalid url" in lowered:
        return "The video URL could not be parsed — check that it is a valid, public video link."

    # No transcript / captions available.
    if "transcript" in lowered and (
        "disabled" in lowered or "no transcript" in lowered or "unavailable" in lowered
    ):
        return (
            "No transcript is available for this source and automatic transcription "
            "failed — the video may have no speech or captions."
        )

    # Anthropic API problems (rate limits, auth, overload).
    if "rate limit" in lowered or "429" in lowered:
        return "Anthropic rate limit hit while extracting steps — retry in a few minutes."
    if "anthropic" in lowered or "api_key" in lowered or "authentication" in lowered:
        return f"The Anthropic API returned an error: {raw}"

    # File-too-large / size limits.
    if "too large" in lowered or "exceeds" in lowered or "413" in lowered:
        return f"The file is too large to process: {raw}"

    # External command failed (yt-dlp / ffmpeg ran but errored).
    if isinstance(exc, subprocess.CalledProcessError):
        stderr = (exc.stderr or b"")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        tool = exc.cmd[0] if isinstance(exc.cmd, (list, tuple)) and exc.cmd else "command"
        detail = (
            stderr.strip().splitlines()[-1]
            if stderr.strip()
            else f"exit code {exc.returncode}"
        )
        return f"{tool} failed while processing the source: {detail}"

    return raw or exc.__class__.__name__
