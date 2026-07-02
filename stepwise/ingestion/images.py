import io
import logging
import zipfile
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
# PIL format names we accept, matched against the decoded image (not the extension).
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

# Upload / ZIP safety limits.
MAX_IMAGE_BYTES = 25 * 1024 * 1024          # 25 MB per decoded image
MAX_TOTAL_UNCOMPRESSED = 500 * 1024 * 1024  # 500 MB expanded across all ZIP entries
MAX_ZIP_ENTRIES = 1000
MAX_COMPRESSION_RATIO = 100                  # per-entry zip-bomb guard


def _is_valid_image(data: bytes) -> bool:
    """Return True if `data` decodes as a supported image format."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()  # detects truncated/corrupt data without a full decode
            return img.format in SUPPORTED_FORMATS
    except Exception:
        return False


def _expand_zip(data: bytes) -> list[tuple[str, bytes]]:
    """Safely extract supported images from a ZIP, guarding against zip bombs."""
    out: list[tuple[str, bytes]] = []
    total_uncompressed = 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise ValueError(f"ZIP has too many entries (max {MAX_ZIP_ENTRIES})")

        for info in infos:
            if info.is_dir():
                continue
            if Path(info.filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            # Reject implausible per-entry sizes / ratios before decompressing.
            if info.file_size > MAX_IMAGE_BYTES:
                raise ValueError("ZIP entry exceeds per-image size limit")
            if (
                info.compress_size > 0
                and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise ValueError("ZIP entry has a suspicious compression ratio")
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_TOTAL_UNCOMPRESSED:
                raise ValueError("ZIP expands beyond the total uncompressed size limit")

            # Strip any directory prefix from zip entries (path-traversal safe).
            name = Path(info.filename).name
            out.append((name, zf.read(info)))
    return out


def ingest_images(files: list[tuple[str, bytes]], output_dir: Path) -> dict:
    """
    Accept a list of (filename, bytes) pairs — either raw images or a single ZIP.
    Saves images to output_dir, sorted by filename.
    Returns {frames: [{path, timestamp}]}
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Expand any ZIP files in the list.
    expanded: list[tuple[str, bytes]] = []
    for filename, data in files:
        if filename.lower().endswith(".zip"):
            expanded.extend(_expand_zip(data))
        elif Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS:
            expanded.append((filename, data))

    # Reject oversized files and anything that isn't actually a valid image.
    verified: list[tuple[str, bytes]] = []
    for filename, data in expanded:
        if len(data) > MAX_IMAGE_BYTES:
            log.warning("Skipping %s: exceeds per-image size limit", filename)
            continue
        if not _is_valid_image(data):
            log.warning("Skipping %s: not a valid image", filename)
            continue
        verified.append((filename, data))

    if not verified:
        raise ValueError("No valid image files found (.jpg, .jpeg, .png, .webp, .gif)")

    # Sort by filename so order is deterministic.
    verified.sort(key=lambda x: x[0].lower())

    frames = []
    for i, (filename, data) in enumerate(verified):
        # Use a zero-padded name to preserve sort order on disk.
        dest = output_dir / f"frame_{i+1:04d}{Path(filename).suffix.lower()}"
        dest.write_bytes(data)
        # Use index * 10 as a synthetic timestamp (10s per image).
        frames.append({"path": str(dest), "timestamp": float(i * 10)})

    return {"frames": frames}
