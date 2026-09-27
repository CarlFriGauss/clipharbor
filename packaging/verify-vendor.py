"""Record vendor provenance without modifying the bundled media tools."""
import hashlib
import json
from pathlib import Path
import zipfile


def digest(stream):
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024*1024), b""):
        value.update(block)
    return value.hexdigest()


root = Path(__file__).resolve().parent.parent
archive_path = root / ".build-tools/ffmpeg-upstream.zip"
result = {"ffmpeg_upstream_release": "https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2024-12-31-13-02",
          "ffmpeg_build_scripts_commit": "7abce16f6a374ff15e8bec186d254c2633747574",
          "tools": {}}
with zipfile.ZipFile(archive_path) as archive:
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        entry = next(item for item in archive.namelist() if item.endswith("/bin/"+name))
        with archive.open(entry) as stream:
            upstream = digest(stream)
        with (root/"packaging/vendor"/name).open("rb") as stream:
            local = digest(stream)
        assert local == upstream, f"{name} does not match the upstream release"
        result["tools"][name] = {"sha256": local, "upstream_verified": True}
with (root/"packaging/vendor/node.exe").open("rb") as stream:
    result["tools"]["node.exe"] = {"version": "22.22.0", "sha256": digest(stream)}
print(json.dumps(result, indent=2))
