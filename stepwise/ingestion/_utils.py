import numpy as np
from PIL import Image


def dedup_frames(frames: list[dict], min_diff: float = 0.04) -> list[dict]:
    """
    Drop near-duplicate consecutive frames using downsampled mean absolute diff.

    min_diff is fraction of max pixel value (0-1). Frames whose thumbnail differs
    from the previous kept frame by less than min_diff are skipped. This reduces
    the number of images sent to Claude without losing meaningful visual transitions.
    """
    if len(frames) <= 1:
        return frames

    kept = [frames[0]]
    first_path = frames[0]["path"]
    if first_path.startswith("http://") or first_path.startswith("https://"):
        return frames  # all URL-based frames — no dedup possible, return as-is
    prev = np.array(Image.open(first_path).resize((32, 32)).convert("L"), dtype=float)

    for frame in frames[1:]:
        path = frame["path"]
        if not path or path.startswith("http://") or path.startswith("https://"):
            kept.append(frame)
            continue
        try:
            curr = np.array(Image.open(path).resize((32, 32)).convert("L"), dtype=float)
        except Exception:
            kept.append(frame)
            continue
        if np.mean(np.abs(curr - prev)) / 255.0 > min_diff:
            kept.append(frame)
            prev = curr

    return kept
