"""
Frame file serving security tests.

There is no Python-side frame HTTP handler in this repository. Screenshot files
are served by the Next.js BFF at:

    web/app/api/frame/route.ts

That route resolves paths relative to DATA_DIR, rejects paths outside DATA_DIR
(403), and returns 404 for missing files.

TODO: add a small JS/Playwright test for web/app/api/frame/route.ts traversal
protection when the web test harness is introduced.
"""

import pytest


@pytest.mark.skip(reason="Frame traversal protection is implemented in Next.js, not Python")
def test_frame_path_traversal_placeholder():
    """Reserved for future web-layer tests — see module docstring."""
