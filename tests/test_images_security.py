"""Tests for image ingestion upload/ZIP safety checks."""

import io
import zipfile

import pytest
from PIL import Image

from stepwise.ingestion.images import ingest_images


def _png_bytes(size: int = 4) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


class TestImageVerification:
    def test_valid_image_accepted(self, tmp_path):
        result = ingest_images([("a.png", _png_bytes())], tmp_path)
        assert len(result["frames"]) == 1
        assert (tmp_path / "frame_0001.png").exists()

    def test_non_image_bytes_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="No valid image"):
            ingest_images([("a.png", b"this is not an image")], tmp_path)

    def test_mislabeled_file_not_written(self, tmp_path):
        # A .png that is actually text must not be written to disk.
        with pytest.raises(ValueError):
            ingest_images([("evil.png", b"<script>")], tmp_path)
        assert list(tmp_path.glob("*")) == []


class TestZipSafety:
    def test_valid_zip_extracts_images(self, tmp_path):
        data = _zip_bytes([("one.png", _png_bytes()), ("two.png", _png_bytes())])
        result = ingest_images([("bundle.zip", data)], tmp_path)
        assert len(result["frames"]) == 2

    def test_too_many_entries_rejected(self, tmp_path):
        data = _zip_bytes([(f"{i}.png", b"") for i in range(1001)])
        with pytest.raises(ValueError, match="too many entries"):
            ingest_images([("bomb.zip", data)], tmp_path)

    def test_high_compression_ratio_rejected(self, tmp_path):
        # 1 MB of zeros compresses to a few KB — a classic zip-bomb signature.
        data = _zip_bytes([("bomb.png", b"\0" * (1024 * 1024))])
        with pytest.raises(ValueError, match="compression ratio"):
            ingest_images([("bomb.zip", data)], tmp_path)
