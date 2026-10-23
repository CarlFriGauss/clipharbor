"""Keep automated tests independent of interactive macOS/Linux account vaults."""
import os

import pytest


@pytest.fixture(autouse=True)
def noninteractive_test_vault(monkeypatch):
    if os.name == "nt":
        return  # Exercise actual user-bound DPAPI on the Windows test machine.
    from mediaforge import publishing
    entries = {}

    class TestVault:
        def __init__(self, path):
            self.path = str(path)
        def read(self):
            return entries.get(self.path, b"{}")
        def write(self, value):
            entries[self.path] = value
        def ensure_available(self):
            pass

    monkeypatch.setattr(publishing, "SecureCredentialStore", TestVault)
