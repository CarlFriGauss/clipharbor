# Bundled tools and notices

ClipHarbor uses FFmpeg and Node as separate executable programs. Their licenses
are not replaced by the application's packaging. See `tools/licenses` and Python
distribution metadata in this bundle for license texts and exact build versions.

- FFmpeg / ffprobe: GPL version 3 or later in this GPL-enabled build.
  Build: N-118197-gbb85423142-20241231, from the developer's existing installation.
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
- yt-dlp-ejs: see its bundled license and source: https://github.com/yt-dlp/ejs
- PyInstaller bootloader: GPL with the PyInstaller distribution exception.
  https://pyinstaller.org/en/stable/license.html

This folder records provenance, not a substitute for corresponding-source
obligations. Before publishing this build publicly, provide the corresponding
source for FFmpeg and its enabled GPL libraries alongside the binary, and review
all third-party redistribution requirements. Do not claim the installer is signed.
