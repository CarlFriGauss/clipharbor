# Bundled tools and notices

ClipHarbor uses FFmpeg and Node as separate executable programs. Their licenses
are not replaced by the application's packaging. See `tools/licenses` and Python
distribution metadata in this bundle for license texts and exact build versions.

- FFmpeg / ffprobe: NOT included in the ClipHarbor installer. First-run setup
  downloads the unmodified archive directly from the BtbN upstream release:
  https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2024-12-31-13-02
  Build: N-118197-gbb85423142-20241231. Its license is saved next to the downloaded tools.
  Archive and binary SHA-256 checksums are pinned in mediaforge/tool_setup.py.
  FFmpeg source: https://github.com/FFmpeg/FFmpeg/tree/bb85423142
  Windows build infrastructure: https://github.com/BtbN/FFmpeg-Builds
  Distribution guidance: https://ffmpeg.org/legal.html
- Node.js v22.22.0: MIT and bundled third-party licenses.
  Source: https://github.com/nodejs/node/tree/v22.22.0
- Python: Python Software Foundation license. https://www.python.org/psf/license/
- Flask and Werkzeug: BSD-3-Clause. https://palletsprojects.com/
- Waitress: ZPL-2.1. https://github.com/Pylons/waitress
- yt-dlp: Unlicense; its dependencies have separate licenses included in metadata.
  https://github.com/yt-dlp/yt-dlp
- Mutagen is an optional yt-dlp dependency for thumbnail tagging. It is excluded
  from this desktop build; ClipHarbor does not use that feature.
- yt-dlp-ejs: see its bundled license and source: https://github.com/yt-dlp/ejs
- PyInstaller bootloader: GPL with the PyInstaller distribution exception.
  https://pyinstaller.org/en/stable/license.html
- Certifi certificate bundle: MPL-2.0. https://github.com/certifi/python-certifi
  Exact Certifi and PyInstaller sources are in ClipHarbor-third-party-sources.zip
  alongside this release: https://github.com/CarlFriGauss/clipharbor/releases/tag/v0.5.1

The installer includes Node and Python license texts and dependency distribution
metadata. FFmpeg is obtained by the end user from its upstream distributor, not
re-hosted as a ClipHarbor release asset. Do not add those binaries to our installer
without first addressing their corresponding-source requirements.
The installer is unsigned.
