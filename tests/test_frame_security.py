"""
Frame file-serving security tests.

Screenshot files are served by the Next.js BFF at ``web/app/api/frame/route.ts``,
which delegates path containment and content-type resolution to the pure helpers
in ``web/app/api/frame/frame-path.ts``. Those helpers have a real test suite
(``web/app/api/frame/route.test.ts``) covering directory traversal, sibling-prefix
bypass, absolute paths, NUL bytes, and the extension allow-list.

This test runs that Node suite via ``node --test`` so the traversal protections
are exercised as part of ``pytest``. It skips (rather than fails) only when Node
is unavailable in the environment.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_WEB_DIR = _REPO_ROOT / "web"
_TEST_FILE = "app/api/frame/route.test.ts"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not available")
def test_frame_route_node_suite_passes():
    """The Node test suite for the frame route's path guards must pass."""
    if not (_WEB_DIR / _TEST_FILE).exists():
        pytest.skip("frame route test file not found")

    result = subprocess.run(
        ["node", "--test", _TEST_FILE],
        cwd=_WEB_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Node frame-route tests failed:\n{result.stdout}\n{result.stderr}"
    )
    # Sanity check that tests actually ran (not a silent no-op).
    assert "pass " in result.stdout and "fail 0" in result.stdout
