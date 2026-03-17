#!/usr/bin/env python3
"""Verify the network sandbox allows and blocks requests correctly."""

import sys
import urllib.error
import urllib.request

ALLOWED_URL = (
    "https://raw.githubusercontent.com"
    "/airutorg/airut/refs/heads/main/README.md"
)
BLOCKED_URL = "https://airut.org/canary.txt"


def test_allowed() -> None:
    """Fetching an allowlisted URL must succeed."""
    resp = urllib.request.urlopen(ALLOWED_URL)
    body = resp.read()
    print(f"PASS: allowed URL returned {resp.status} ({len(body)} bytes)")


def test_blocked() -> None:
    """Fetching a non-allowlisted URL must return 403."""
    try:
        urllib.request.urlopen(BLOCKED_URL)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("PASS: blocked URL returned 403")
            return
        print(f"FAIL: blocked URL returned {e.code}, expected 403")
        sys.exit(1)
    except urllib.error.URLError as e:
        # Connection refused or DNS failure is also acceptable — the
        # proxy may reject at the connection level depending on config.
        print(f"PASS: blocked URL connection failed ({e.reason})")
        return

    print("FAIL: blocked URL was not blocked")
    sys.exit(1)


if __name__ == "__main__":
    test_allowed()
    test_blocked()
    print("All network sandbox tests passed")
