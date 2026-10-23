"""Store connection tokens with the current user's operating-system protection."""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


class CredentialStoreError(RuntimeError):
    pass


def _dpapi(raw: bytes, decrypt=False) -> bytes:
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    if decrypt:
        ok = ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else:
        ok = ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), "ClipHarbor", None, None, None, 1, ctypes.byref(output))
    if not ok:
        raise CredentialStoreError("Windows could not unlock the saved connection. Sign in again from your own Windows account.")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)


class SecureCredentialStore:
    """DPAPI on Windows; Keychain or Secret Service elsewhere. No plaintext fallback."""

    def __init__(self, path):
        self.path = Path(path)
        self.platform = sys.platform
        self.account = hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()

    def _run(self, command, *, data=None, missing=()):
        try:
            result = subprocess.run(command, input=data, capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise CredentialStoreError("The operating system's secure credential store is unavailable. Unlock it before connecting Google Drive.") from None
        if result.returncode in missing:
            return None
        if result.returncode:
            raise CredentialStoreError("The operating system could not save or unlock this connection securely. No unencrypted token file was created.")
        return result.stdout.strip()

    def _native_read(self):
        if self.platform == "darwin":
            return self._run(["/usr/bin/security", "find-generic-password", "-s", "ClipHarbor", "-a", self.account, "-w"], missing=(44,))
        return self._run(["/usr/bin/secret-tool", "lookup", "application", "ClipHarbor", "account", self.account], missing=(1,))

    def ensure_available(self):
        if self.platform != "win32":
            self._native_read()

    def read(self):
        if self.platform == "win32":
            return _dpapi(self.path.read_bytes(), decrypt=True) if self.path.exists() else b"{}"
        encoded = self._native_read()
        if encoded:
            try:
                return base64.b64decode(encoded, validate=True)
            except ValueError:
                raise CredentialStoreError("The saved connection is damaged. Disconnect and sign in again.") from None
        # Migrate files written by the previous source build into the OS vault.
        # Delete the old file only after its protected replacement is confirmed.
        if self.path.is_symlink():
            raise CredentialStoreError("The legacy credential file cannot be migrated safely.")
        if self.path.exists():
            raw = self.path.read_bytes()
            try:
                if not isinstance(json.loads(raw), dict):
                    raise ValueError
            except ValueError:
                raise CredentialStoreError("The saved connection is damaged. Sign in again.") from None
            self.write(raw)
            self.path.unlink()
            return raw
        return b"{}"

    def write(self, raw: bytes):
        if self.platform == "win32":
            protected = _dpapi(raw)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix="accounts-", suffix=".tmp", dir=self.path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(protected)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            return
        encoded = base64.b64encode(raw)
        if self.platform == "darwin":
            # Feed the secret through stdin, never through visible process arguments.
            command = b"add-generic-password -U -s ClipHarbor -a " + self.account.encode() + b" -w " + encoded + b"\n"
            self._run(["/usr/bin/security", "-i"], data=command)
        else:
            self._run(["/usr/bin/secret-tool", "store", "--label=ClipHarbor connection", "application", "ClipHarbor", "account", self.account], data=encoded)
        if self._native_read() != encoded:
            raise CredentialStoreError("The operating system did not confirm secure storage. Please try connecting again.")
