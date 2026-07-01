import io
import zipfile
from pathlib import Path

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def ingest_images(files: list[tuple[str, bytes]], output_dir: Path) -> dict:
    """
    Accept a list of (filename, bytes) pairs — either raw images or a single ZIP.
    Saves images to output_dir, sorted by filename.
    Returns {title, frames: [{path, timestamp}]}
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Expand any ZIP files in the list
    expanded: list[tuple[str, bytes]] = []
    for filename, data in files:
        if filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for entry in zf.namelist():
                    if Path(entry).suffix.lower() in SUPPORTED_EXTENSIONS:
                        # Strip any directory prefix from zip entries
                        name = Path(entry).name
                        expanded.append((name, zf.read(entry)))
        elif Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS:
            expanded.append((filename, data))

    if not expanded:
        raise ValueError("No supported image files found (.jpg, .jpeg, .png, .webp)")

    # Sort by filename so order is deterministic
    expanded.sort(key=lambda x: x[0].lower())

    frames = []
    for i, (filename, data) in enumerate(expanded):
        # Use a zero-padded name to preserve sort order on disk
        dest = output_dir / f"frame_{i+1:04d}{Path(filename).suffix.lower()}"
        dest.write_bytes(data)
        # Use index * 10 as a synthetic timestamp (10s per image)
        frames.append({"path": str(dest), "timestamp": float(i * 10)})

    return {"frames": frames}
