import anthropic

from stepwise.config import settings
from stepwise.models import Step

_client = None

CONSOLIDATE_TOOL = {
    "name": "consolidate_steps",
    "description": "Consolidate a list of tutorial steps into a smaller, cleaner set.",
    "input_schema": {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_step_number": {
                            "type": "integer",
                            "description": (
                                "Step number from the original list to inherit "
                                "visual/timestamp from"
                            ),
                        },
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "action_type": {
                            "type": "string",
                            "enum": ["click", "configure", "navigate", "explain", "verify"],
                        },
                    },
                    "required": ["source_step_number", "title", "description", "action_type"],
                },
            }
        },
        "required": ["steps"],
    },
}

SYSTEM_PROMPT = (
    "You are a tutorial editor. You will receive a list of raw steps extracted from a "
    "tutorial video and must consolidate them into a clean, minimal set.\n"
    "\n"
    "Rules:\n"
    "- Target exactly the number of steps specified by the user.\n"
    "- Merge adjacent steps that are part of the same action.\n"
    '- Drop non-instructional steps: intros, outros, "like and subscribe", filler commentary.\n'
    "- Drop duplicate or near-duplicate steps.\n"
    "- Each output step must reference a source_step_number from the input (the step whose "
    "screenshot and timestamp should be used).\n"
    "- Descriptions should be clear and actionable in 1-3 sentences."
)


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def consolidate_steps(steps: list[Step], target_count: int) -> list[Step]:
    """Merge and clean steps down to approximately target_count."""
    if len(steps) <= target_count:
        return steps

    # Build a compact text representation (no images — too expensive for a full list)
    steps_text = "\n".join(
        f"{s.step_number}. [{s.action_type}] {s.title}: {s.description}"
        for s in steps
    )

    response = _get_client().messages.create(
        model=settings.consolidation_model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[CONSOLIDATE_TOOL],
        tool_choice={"type": "tool", "name": "consolidate_steps"},
        messages=[{
            "role": "user",
            "content": (
                f"Consolidate these {len(steps)} steps into approximately "
                f"{target_count} steps.\n\n{steps_text}"
            ),
        }],
    )

    tool_use = next(b for b in response.content if b.type == "tool_use")
    consolidated = tool_use.input["steps"]

    # Build a lookup for original steps
    step_by_number = {s.step_number: s for s in steps}

    result = []
    for i, item in enumerate(consolidated, start=1):
        source = step_by_number.get(item["source_step_number"], steps[0])
        result.append(Step(
            id=source.id,
            tutorial_id=source.tutorial_id,
            step_number=i,
            title=item["title"],
            description=item["description"],
            action_type=item["action_type"],
            visual_reference=source.visual_reference,
            timestamp_start=source.timestamp_start,
            timestamp_end=source.timestamp_end,
            transcript_source=source.transcript_source,
            confidence_score=source.confidence_score,
        ))

    return result
