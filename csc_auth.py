#!/usr/bin/env python
"""Authenticated CSC envelope primitives.

This module detects accidental or unauthorized message injection when the
session key remains secret. It is not a sandbox against malware already
running as the same OS user, which can generally read the same local files.
"""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import hmac
import json
import math
import re
import secrets
import threading
import time
from typing import Any, Dict, MutableSet, Optional


AUTH_VERSION = "csc-hmac-sha256-v1"
MIN_KEY_BYTES = 32
DEFAULT_MAX_SKEW_SECONDS = 30.0
_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
_MAC_RE = re.compile(r"^[0-9a-f]{64}$")


class AuthenticationError(ValueError):
    """Raised when an envelope cannot be authenticated."""


class ReplayError(AuthenticationError):
    """Raised when an already accepted nonce is presented again."""


class ReplayWindow:
    """Bounded, fail-closed nonce memory for one authenticated epoch."""

    def __init__(self, ttl_seconds: float = 60.0, max_entries: int = 4096) -> None:
        try:
            ttl = float(ttl_seconds)
        except (TypeError, ValueError) as exc:
            raise AuthenticationError("replay TTL must be a number") from exc
        if not math.isfinite(ttl) or ttl <= 0:
            raise AuthenticationError("replay TTL must be finite and positive")
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries < 1:
            raise AuthenticationError("replay capacity must be a positive integer")
        self.ttl_seconds = ttl
        self.max_entries = max_entries
        self._entries: "OrderedDict[str, float]" = OrderedDict()
        self._lock = threading.Lock()

    def check_and_add(self, nonce: str, accepted_at: float) -> None:
        try:
            now = float(accepted_at)
        except (TypeError, ValueError) as exc:
            raise AuthenticationError("replay timestamp must be a number") from exc
        if not math.isfinite(now):
            raise AuthenticationError("replay timestamp must be finite")
        with self._lock:
            cutoff = now - self.ttl_seconds
            while self._entries:
                oldest_nonce, oldest_at = next(iter(self._entries.items()))
                if oldest_at > cutoff:
                    break
                self._entries.pop(oldest_nonce)
            if nonce in self._entries:
                raise ReplayError("message nonce has already been accepted")
            if len(self._entries) >= self.max_entries:
                raise AuthenticationError("replay window capacity exhausted")
            self._entries[nonce] = now


def generate_session_key() -> bytes:
    """Return a new 256-bit session key from the operating system CSPRNG."""
    return secrets.token_bytes(MIN_KEY_BYTES)


def _validate_key(key: bytes) -> None:
    if not isinstance(key, bytes) or len(key) < MIN_KEY_BYTES:
        raise AuthenticationError("session key must contain at least 32 bytes")


def _canonical_bytes(message: Dict[str, Any], auth_fields: Dict[str, Any]) -> bytes:
    payload = {"auth": auth_fields, "message": message}
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("envelope is not canonical JSON") from exc
    return encoded.encode("utf-8")


def _message_without_auth(envelope: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(envelope, dict):
        raise AuthenticationError("envelope must be an object")
    return {key: value for key, value in envelope.items() if key != "auth"}


def sign_envelope(
    envelope: Dict[str, Any],
    key: bytes,
    epoch: str,
    *,
    issued_at: Optional[float] = None,
    nonce: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a signed copy without mutating the caller's envelope."""
    _validate_key(key)
    if not isinstance(epoch, str) or not epoch.strip():
        raise AuthenticationError("epoch must be a non-empty string")
    timestamp = time.time() if issued_at is None else float(issued_at)
    if not math.isfinite(timestamp):
        raise AuthenticationError("issued_at must be finite")
    selected_nonce = nonce or secrets.token_hex(16)
    if not isinstance(selected_nonce, str) or not _NONCE_RE.fullmatch(selected_nonce):
        raise AuthenticationError("nonce must be 16 bytes encoded as lowercase hex")

    message = _message_without_auth(envelope)
    auth_fields: Dict[str, Any] = {
        "version": AUTH_VERSION,
        "epoch": epoch,
        "issued_at": timestamp,
        "nonce": selected_nonce,
    }
    mac = hmac.new(key, _canonical_bytes(message, auth_fields), hashlib.sha256).hexdigest()
    return {**message, "auth": {**auth_fields, "mac": mac}}


def verify_envelope(
    envelope: Dict[str, Any],
    key: bytes,
    expected_epoch: str,
    *,
    now: Optional[float] = None,
    max_skew_seconds: float = DEFAULT_MAX_SKEW_SECONDS,
    seen_nonces: Optional[MutableSet[str]] = None,
    replay_window: Optional[ReplayWindow] = None,
) -> Dict[str, Any]:
    """Verify freshness, epoch, integrity and replay state; return message copy."""
    _validate_key(key)
    message = _message_without_auth(envelope)
    auth = envelope.get("auth")
    if not isinstance(auth, dict):
        raise AuthenticationError("missing authentication metadata")
    required = {"version", "epoch", "issued_at", "nonce", "mac"}
    if set(auth) != required:
        raise AuthenticationError("authentication metadata fields are invalid")
    if auth["version"] != AUTH_VERSION:
        raise AuthenticationError("unsupported authentication version")
    if auth["epoch"] != expected_epoch:
        raise AuthenticationError("session epoch mismatch")
    nonce = auth["nonce"]
    mac = auth["mac"]
    if not isinstance(nonce, str) or not _NONCE_RE.fullmatch(nonce):
        raise AuthenticationError("invalid nonce")
    if not isinstance(mac, str) or not _MAC_RE.fullmatch(mac):
        raise AuthenticationError("invalid message authentication code")
    try:
        issued_at = float(auth["issued_at"])
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("invalid issued_at") from exc
    try:
        check_time = time.time() if now is None else float(now)
        allowed_skew = float(max_skew_seconds)
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("time values must be numbers") from exc
    if not all(math.isfinite(value) for value in (issued_at, check_time, allowed_skew)):
        raise AuthenticationError("timestamps must be finite")
    if allowed_skew < 0 or abs(check_time - issued_at) > allowed_skew:
        raise AuthenticationError("message timestamp is outside the accepted window")

    auth_fields = {key_name: auth[key_name] for key_name in required if key_name != "mac"}
    expected = hmac.new(key, _canonical_bytes(message, auth_fields), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, mac):
        raise AuthenticationError("message authentication failed")
    if replay_window is not None and seen_nonces is not None:
        raise AuthenticationError("choose one replay state implementation")
    if replay_window is not None:
        replay_window.check_and_add(nonce, check_time)
    if seen_nonces is not None:
        if nonce in seen_nonces:
            raise ReplayError("message nonce has already been accepted")
        seen_nonces.add(nonce)
    return message
