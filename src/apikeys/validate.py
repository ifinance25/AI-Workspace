"""Validation for Anthropic API keys: offline format check + live probe.

Two independent checks, cheapest first:

* :func:`validate_key_format` — a pure regex test against
  :data:`KEY_PATTERN`. No I/O, so it is safe to run on every form submission
  before spending a network round-trip.
* :func:`probe_key` — an async ``GET /v1/models`` against the Anthropic API to
  confirm the key is actually accepted. It never raises: any timeout, network
  error, or unexpected status collapses to :attr:`ProbeResult.UNKNOWN` so
  callers can treat "couldn't tell" separately from "definitely bad".
"""
from __future__ import annotations

import asyncio
import enum
import re

import aiohttp

#: Anthropic keys look like ``sk-ant-...`` followed by a long token drawn from
#: ``[a-zA-Z0-9-_]``. We require at least 40 such characters after the prefix;
#: real keys are far longer, so this rejects obvious junk while staying lenient
#: about the exact suffix format (which Anthropic has changed over time).
KEY_PATTERN = re.compile(r"^sk-ant-[a-zA-Z0-9\-_]{40,}$")

#: Endpoint used to probe a key. Listing models is the cheapest authenticated
#: call and does not mutate anything.
_MODELS_URL = "https://api.anthropic.com/v1/models"

#: Header pinning the stable Anthropic API version (see their docs).
_ANTHROPIC_VERSION = "2023-06-01"

#: Identifies our probe traffic in Anthropic's logs.
_USER_AGENT = "vels-claude-bot/1.0"


class ProbeResult(enum.Enum):
    """Outcome of a live :func:`probe_key` check."""

    VALID = "valid"      # API accepted the key (HTTP 200)
    INVALID = "invalid"  # API rejected the key (HTTP 401 / 403)
    UNKNOWN = "unknown"  # couldn't determine (timeout, network error, other)


_OPENAI_PATTERN = re.compile(r"^sk-[A-Za-z0-9_-]{16,}$")
_GENERIC_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9._-]{12,}$")


def validate_key_format(
    key: str,
    *,
    provider: str = "claude",
    auth_kind: str = "api_key",
) -> bool:
    """Return ``True`` iff ``key`` looks like a key for ``provider``.

    Offline check only — a ``True`` result means the string is *shaped* like a
    key, not that it is live. ``None``, empty, or malformed input returns
    ``False`` rather than raising. Default ``provider='claude'`` keeps the
    historical Anthropic ``sk-ant-`` check for ``/api/apikey``.
    """
    if not key:
        return False
    if auth_kind == "oauth":
        return len(key.strip()) >= 20
    if provider == "claude":
        return KEY_PATTERN.match(key) is not None
    if provider == "openai":
        return _OPENAI_PATTERN.match(key) is not None and not key.startswith("sk-ant-")
    if provider == "kimi":
        return _OPENAI_PATTERN.match(key) is not None
    if provider == "cursor":
        return _GENERIC_SECRET_PATTERN.match(key) is not None
    return len(key.strip()) >= 16


async def probe_key(
    key: str, timeout: float = 10.0, *, provider: str = "claude"
) -> ProbeResult:
    """Check ``key`` against the Anthropic API and classify the response.

    Performs ``GET /v1/models`` with the key in the ``x-api-key`` header and
    maps the outcome:

    * HTTP 200            -> :attr:`ProbeResult.VALID`
    * HTTP 401 / 403      -> :attr:`ProbeResult.INVALID`
    * anything else, or a timeout / network error / unexpected exception
                          -> :attr:`ProbeResult.UNKNOWN`

    This function never raises; failures are reported as ``UNKNOWN`` so a
    transient outage is not mistaken for a bad key.

    Args:
        key: The API key to test.
        timeout: Total request timeout in seconds (default 10).
        provider: Live Anthropic probe runs only for ``claude``. Other
            providers are accepted after the offline format check.
    """
    if provider != "claude":
        return ProbeResult.VALID
    headers = {
        "x-api-key": key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "user-agent": _USER_AGENT,
    }
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(_MODELS_URL, headers=headers) as response:
                if response.status == 200:
                    return ProbeResult.VALID
                if response.status in (401, 403):
                    return ProbeResult.INVALID
                return ProbeResult.UNKNOWN
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        return ProbeResult.UNKNOWN
    except Exception:
        # Belt-and-braces: a probe must never propagate an error to the caller.
        return ProbeResult.UNKNOWN
