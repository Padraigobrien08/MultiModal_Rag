"""Integration tests for the unified ingestion pipeline."""

from unittest.mock import MagicMock, patch

from stepwise.ingestion.pipeline import (
    JobTracker,
    finalize_steps,
    image_consolidation_target,
    run_ingestion_pipeline,
    video_consolidation_target,
)
from stepwise.models import Segment, Step


def _step(n: int, title: str = "Do thing", end: float = 60.0) -> Step:
    return Step(
        id=f"step-{n}",
        tutorial_id="tut-1",
        step_number=n,
        title=title,
        description=f"Description {n}",
        timestamp_end=end,
    )


def _segment(text: str = "click save") -> Segment:
    return Segment(time_start=0.0, time_end=10.0, transcript=text, frame_paths=[])


class TestConsolidationTargets:
    def test_video_target_scales_with_duration(self):
        steps = [_step(i, end=120) for i in range(1, 15)]
        assert video_consolidation_target(steps) == 10

    def test_video_target_none_when_few_steps(self):
        steps = [_step(1, end=30)]
        assert video_consolidation_target(steps) is None

    def test_image_target_when_many_steps(self):
        steps = [_step(i) for i in range(1, 25)]
        assert image_consolidation_target(steps, frame_count=20) == 20


class TestFinalizeSteps:
    def test_dedup_and_filter_applied(self):
        steps = [
            _step(1, "Save file"),
            _step(2, "Save file"),
        ]
        with patch(
            "stepwise.ingestion.pipeline.deduplicate_steps", side_effect=lambda s: s[:1]
        ) as dedup:
            with patch(
                "stepwise.ingestion.pipeline.filter_trivial_steps", side_effect=lambda s: s
            ) as filt:
                result = finalize_steps(steps, JobTracker(None))
        assert len(result) == 1
        dedup.assert_called_once()
        filt.assert_called_once()


class TestRunIngestionPipeline:
    def test_full_pipeline_with_prebuilt_segments(self):
        segments = [_segment(), _segment("next part")]
        fake_steps = [_step(1), _step(2)]

        with patch(
            "stepwise.ingestion.pipeline.structure_segments", return_value=fake_steps
        ) as struct:
            with patch(
                "stepwise.ingestion.pipeline.finalize_steps", return_value=fake_steps
            ) as fin:
                with patch("stepwise.ingestion.pipeline.index_tutorial_result") as index:
                    with patch("stepwise.ingestion.pipeline.align_segments") as align:
                        tutorial = run_ingestion_pipeline(
                            source_url="https://example.com/v",
                            title="Demo",
                            source_type="youtube",
                            meta={"video_id": "vid1"},
                            transcript=[],
                            frames=[],
                            tutorial_id="tut-pipe",
                            segments=segments,
                            consolidation_target_fn=video_consolidation_target,
                        )

        align.assert_not_called()
        struct.assert_called_once()
        fin.assert_called_once()
        index.assert_called_once()
        assert tutorial.id == "tut-pipe"
        assert len(tutorial.steps) == 2

    def test_pipeline_aligns_when_segments_omitted(self):
        transcript = [{"text": "hi", "start": 0, "duration": 1}]
        frames = [{"path": "/f.jpg", "timestamp": 0}]
        built = [_segment()]

        with patch("stepwise.ingestion.pipeline.align_segments", return_value=built) as align:
            with patch("stepwise.ingestion.pipeline.structure_segments", return_value=[_step(1)]):
                with patch("stepwise.ingestion.pipeline.finalize_steps", return_value=[_step(1)]):
                    with patch("stepwise.ingestion.pipeline.index_tutorial_result"):
                        run_ingestion_pipeline(
                            source_url="https://example.com/v",
                            title="Demo",
                            source_type="youtube",
                            meta={},
                            transcript=transcript,
                            frames=frames,
                            tutorial_id="tut-align",
                        )

        align.assert_called_once_with(transcript, frames)


class TestJobTracker:
    def test_no_op_without_job_id(self):
        tracker = JobTracker(None)
        tracker.set_stage("indexing")
        tracker.complete("tut", 3)

    def test_updates_job_in_db(self):
        job = MagicMock()
        job.segments_done = 0
        session = MagicMock()
        session.get.return_value = job
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=session)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch("stepwise.ingestion.pipeline.get_db_session", return_value=ctx):
            tracker = JobTracker("job-1")
            tracker.start_running("aligning")
            tracker.segment_done()
            tracker.complete("tut-9", 4)

        assert job.status == "done"
        assert job.tutorial_id == "tut-9"
        assert job.step_count == 4


class TestYouTubeIngestionTask:
    def test_run_youtube_ingestion_delegates_to_pipeline(self):
        artifacts = {
            "title": "My Video",
            "video_id": "abc123",
            "transcript": [{"text": "t", "start": 0, "duration": 1}],
            "frames": [],
        }

        with patch("stepwise.ingestion.tasks.ingest_youtube", return_value=artifacts):
            with patch("stepwise.ingestion.tasks.run_ingestion_pipeline") as pipeline:
                from stepwise.ingestion.tasks import run_youtube_ingestion

                run_youtube_ingestion("job-1", "https://youtube.com/watch?v=abc123", "Override")

        pipeline.assert_called_once()
        kwargs = pipeline.call_args.kwargs
        assert kwargs["title"] == "Override"
        assert kwargs["job_id"] == "job-1"
        assert kwargs["meta"]["video_id"] == "abc123"
