"""Verify the network sandbox allows and blocks requests correctly."""

import urllib.error
import urllib.request


ALLOWED_URL = (
    "https://raw.githubusercontent.com/airutorg/airut/refs/heads/main/README.md"
)
BLOCKED_URL = "https://airut.org/canary.txt"


def test_allowed_url_is_reachable() -> None:
    """Fetching an allowlisted URL must succeed."""
    resp = urllib.request.urlopen(ALLOWED_URL)
    body = resp.read()
    assert resp.status == 200
    assert len(body) > 0


def test_blocked_url_returns_403() -> None:
    """Fetching a non-allowlisted URL must be blocked by the proxy."""
    try:
        urllib.request.urlopen(BLOCKED_URL)
    except urllib.error.HTTPError as e:
        assert e.code == 403, f"Expected 403, got {e.code}"
        return
    except urllib.error.URLError:
        # Connection refused or DNS failure is also acceptable —
        # the proxy may reject at the connection level.
        return

    raise AssertionError("Blocked URL was not blocked")
