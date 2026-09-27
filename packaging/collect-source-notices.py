"""Fetch exact upstream source archives for source-licensed bundled components."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
from urllib.request import urlopen
import zipfile


root = Path(__file__).resolve().parent.parent
destination = root / "dist/installer/ClipHarbor-third-party-sources.zip"
manifest = []
with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as bundle:
    for package in ("certifi", "pyinstaller"):
        release = version(package)
        with urlopen(f"https://pypi.org/pypi/{package}/{release}/json", timeout=30) as response:
            metadata = json.load(response)
        source = next(item for item in metadata["urls"] if item["packagetype"] == "sdist")
        with urlopen(source["url"], timeout=60) as response:
            data = response.read()
        assert hashlib.sha256(data).hexdigest() == source["digests"]["sha256"]
        bundle.writestr(source["filename"], data)
        manifest.append({"package": package, "version": release, "url": source["url"],
                         "sha256": source["digests"]["sha256"]})
    bundle.writestr("sources.json", json.dumps(manifest, indent=2))
print(destination)
