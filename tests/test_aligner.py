"""Tests for transcript/frame alignment into Segment objects."""

from stepwise.alignment.aligner import _make_segment, _target_words, align_segments
from stepwise.models import Segment


def _entry(text: str, start: float, duration: float = 2.0) -> dict:
    return {"text": text, "start": start, "duration": duration}


class TestAlignSegments:
    def test_empty_transcript_returns_empty_list(self):
        assert align_segments([], [{"path": "/f.jpg", "timestamp": 0}]) == []

    def test_single_short_transcript_produces_one_segment(self):
        transcript = [_entry("Click Settings. Then save.", start=0, duration=5)]
        frames = [{"path": "/frames/a.jpg", "timestamp": 2}]

        segments = align_segments(transcript, frames)

        assert len(segments) == 1
        seg = segments[0]
        assert isinstance(seg, Segment)
        assert seg.transcript == "Click Settings. Then save."
        assert seg.time_start == 0
        assert seg.time_end == 5
        assert seg.frame_paths == ["/frames/a.jpg"]

    def test_frames_assigned_by_timestamp_inclusive_bounds(self):
        entries = [
            _entry("First segment content.", start=0, duration=10),
            _entry("Second segment content.", start=10, duration=10),
        ]
        frames = [
            {"path": "/early.jpg", "timestamp": 0},
            {"path": "/mid.jpg", "timestamp": 5},
            {"path": "/boundary.jpg", "timestamp": 10},
            {"path": "/late.jpg", "timestamp": 19},
            {"path": "/outside.jpg", "timestamp": 25},
        ]

        first = _make_segment([entries[0]], frames)
        second = _make_segment([entries[1]], frames)

        assert first.frame_paths == ["/early.jpg", "/mid.jpg", "/boundary.jpg"]
        assert second.frame_paths == ["/boundary.jpg", "/late.jpg"]
        assert "/outside.jpg" not in first.frame_paths + second.frame_paths

    def test_long_transcript_splits_into_multiple_segments(self):
        # Short video (<10 min) splits at min_words=50 on sentence boundaries.
        sentences = [f"{'alpha beta ' * 6}chunk {i} ends." for i in range(12)]
        transcript = []
        t = 0.0
        for sentence in sentences:
            transcript.append(_entry(sentence, start=t, duration=1.0))
            t += 1.0

        segments = align_segments(transcript, [])

        assert len(segments) >= 2
        total_words = sum(len(s.transcript.split()) for s in segments)
        assert total_words == sum(len(s.split()) for s in sentences)
        for seg in segments:
            assert seg.time_end > seg.time_start

    def test_splits_on_max_word_count_even_without_sentence_end(self):
        # Force max_words flush: one long entry without terminal punctuation.
        long_text = " ".join(["word"] * 85)
        transcript = [_entry(long_text, start=0, duration=60)]

        segments = align_segments(transcript, [])

        assert len(segments) == 1
        assert len(segments[0].transcript.split()) == 85

    def test_target_words_scales_with_duration(self):
        assert _target_words(5 * 60) == (50, 80)
        assert _target_words(20 * 60) == (80, 130)
        assert _target_words(45 * 60) == (130, 200)
        assert _target_words(90 * 60) == (200, 300)
