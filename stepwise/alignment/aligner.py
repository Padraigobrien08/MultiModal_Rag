from stepwise.models import Segment

SENTENCE_END = {".", "?", "!"}


def _target_words(duration_seconds: float) -> tuple[int, int]:
    """Return (min_words, max_words) based on video duration."""
    minutes = duration_seconds / 60
    if minutes < 10:
        return 50, 80       # short: fine-grained
    elif minutes < 30:
        return 80, 130      # medium
    elif minutes < 60:
        return 130, 200     # long
    else:
        return 200, 300     # very long


def align_segments(transcript: list[dict], frames: list[dict]) -> list[Segment]:
    """
    Groups transcript entries into semantic segments by splitting on sentence
    boundaries. Window size scales with video duration so longer videos produce
    proportionally fewer, larger segments.

    transcript: [{text, start, duration}, ...]
    frames:     [{path, timestamp}, ...]
    """
    if not transcript:
        return []

    last_entry = transcript[-1]
    duration = last_entry["start"] + last_entry.get("duration", 0)
    min_words, max_words = _target_words(duration)

    segments = []
    bucket: list[dict] = []
    word_count = 0

    for entry in transcript:
        bucket.append(entry)
        word_count += len(entry["text"].split())
        ends_sentence = entry["text"].rstrip().endswith(tuple(SENTENCE_END))

        if (word_count >= min_words and ends_sentence) or word_count >= max_words:
            segments.append(_make_segment(bucket, frames))
            bucket = []
            word_count = 0

    if bucket:
        segments.append(_make_segment(bucket, frames))

    return segments


def _make_segment(entries: list[dict], frames: list[dict]) -> Segment:
    time_start = entries[0]["start"]
    last = entries[-1]
    time_end = last["start"] + last.get("duration", 0)

    frame_paths = [
        f["path"] for f in frames
        if time_start <= f["timestamp"] <= time_end
    ]

    return Segment(
        time_start=time_start,
        time_end=time_end,
        transcript=" ".join(e["text"] for e in entries),
        frame_paths=frame_paths,
    )
