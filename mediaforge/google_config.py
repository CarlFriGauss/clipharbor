"""Publisher-owned Google OAuth registration, separate from each user's tokens."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .runtime import RESOURCE_ROOT


class GoogleConfigurationError(ValueError):
    pass


def google_client(legacy_account=None):
    """End users only sign in; registration is supplied by the app publisher."""
    client_id = os.environ.get("CLIPHARBOR_GOOGLE_CLIENT_ID", "").strip()
    if client_id:
        installed = {"client_id": client_id, "client_secret": os.environ.get("CLIPHARBOR_GOOGLE_CLIENT_SECRET", "")}
    else:
        override = os.environ.get("CLIPHARBOR_GOOGLE_CLIENT_FILE")
        path = Path(override).expanduser() if override else RESOURCE_ROOT / "google-oauth-client.json"
        if not override and not path.exists():
            # Public native-app identity, also shipped in the installer. This
            # contains no signed-in user's access or refresh tokens.
            path = RESOURCE_ROOT / "publisher" / "google-oauth-client.json"
        if path.exists():
            try:
                installed = json.loads(path.read_text(encoding="utf-8")).get("installed", {})
            except (OSError, ValueError, AttributeError):
                raise GoogleConfigurationError("Google sign-in is not configured correctly in this ClipHarbor build.") from None
        elif override:
            raise GoogleConfigurationError("Google sign-in is not configured correctly in this ClipHarbor build.")
        else:
            installed = legacy_account or {}
    if not isinstance(installed, dict) or not isinstance(installed.get("client_id"), str) or not installed["client_id"].strip():
        raise GoogleConfigurationError("Google sign-in is not available in this ClipHarbor build yet. The publisher needs to configure it once; users only need to sign in.")
    return {"installed": {"client_id": installed["client_id"].strip(), "client_secret": str(installed.get("client_secret", ""))}}
