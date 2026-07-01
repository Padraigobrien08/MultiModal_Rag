import base64
import time
import uuid
from pathlib import Path

import anthropic

from stepwise.config import settings
from stepwise.models import Segment, Step
from stepwise.structuring.deduplicator import deduplicate_steps

_client = None

EXTRACT_STEPS_TOOL = {
    "name": "extract_steps",
    "description": "Extract structured procedural steps from a tutorial segment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Short action title, max 10 words",
                        },
                        "description": {
                            "type": "string",
                            "description": "Clear instruction a user can follow, 1-3 sentences",
                        },
                        "action_type": {
                            "type": "string",
                            "enum": ["click", "configure", "navigate", "explain", "verify"],
                        },
                        "confidence": {
                            "type": "number",
                            "description": "0.0-1.0, how clearly this is a distinct step",
                        },
                    },
                    "required": ["title", "description", "action_type", "confidence"],
                },
            }
        },
        "required": ["steps"],
    },
}

SYSTEM_PROMPT = (
    "You are a tutorial analysis assistant. Given a transcript segment and/or "
    "screenshots from a tutorial, extract the procedural steps a user must perform. "
    "If only screenshots are provided with no transcript, infer the steps from what "
    "is visible in the UI. Call the extract_steps tool with your findings."
)

USER_TEMPLATE = "Transcript segment ({start:.0f}s – {end:.0f}s):\n{transcript}"
IMAGE_ONLY_TEMPLATE = "Screenshot {index} of {total}. Extract the step shown."


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


# Cached system message — reused across all segment calls in a session
_SYSTEM_MESSAGE = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _media_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {"jpg": "image/jpeg", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/jpeg")


def _build_messages(segment: Segment, image_index: int = 0, total_images: int = 0) -> list[dict]:
    content: list[dict] = []

    for frame_path in segment.frame_paths[:2]:
        if Path(frame_path).exists():
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _media_type(frame_path),
                    "data": _encode_image(frame_path),
                },
            })

    if segment.transcript.strip():
        text = USER_TEMPLATE.format(
            start=segment.time_start, end=segment.time_end, transcript=segment.transcript
        )
    else:
        text = IMAGE_ONLY_TEMPLATE.format(index=image_index, total=total_images)

    content.append({"type": "text", "text": text})
    return [{"role": "user", "content": content}]


def structure_segment(tutorial_id: str, segment: Segment, step_number_start: int,
                      image_index: int = 0, total_images: int = 0) -> list[Step]:
    """Structure a single segment into steps. Returns the steps extracted."""
    max_retries = 4
    for attempt in range(max_retries):
        try:
            response = _get_client().messages.create(
                model=settings.structuring_model,
                max_tokens=1024,
                system=_SYSTEM_MESSAGE,
                tools=[EXTRACT_STEPS_TOOL],
                tool_choice={"type": "tool", "name": "extract_steps"},
                messages=_build_messages(
                    segment, image_index=image_index, total_images=total_images
                ),
                betas=["prompt-caching-2024-07-31"],
            )
            break
        except anthropic.RateLimitError:
            if attempt == max_retries - 1:
                raise
            wait = 30 * (attempt + 1)  # 30s, 60s, 90s
            time.sleep(wait)

    tool_use = next(b for b in response.content if b.type == "tool_use")
    steps = []
    for i, item in enumerate(tool_use.input.get("steps", [])):
        steps.append(Step(
            id=str(uuid.uuid4()),
            tutorial_id=tutorial_id,
            step_number=step_number_start + i,
            title=item["title"],
            description=item["description"],
            action_type=item["action_type"],
            visual_reference=segment.frame_paths[0] if segment.frame_paths else None,
            timestamp_start=segment.time_start,
            timestamp_end=segment.time_end,
            transcript_source=segment.transcript,
            confidence_score=item["confidence"],
        ))
    return steps


def structure_steps(tutorial_id: str, segments: list[Segment]) -> list[Step]:
    all_steps: list[Step] = []
    step_number = 1
    for segment in segments:
        steps = structure_segment(tutorial_id, segment, step_number)
        all_steps.extend(steps)
        step_number += len(steps)
    return deduplicate_steps(all_steps)
