# Building the Windows installer

This is the existing ClipHarbor application, not a rewrite. PyInstaller makes a
windowless one-folder application; Inno Setup wraps it in a per-user installer.
The browser remains the interface. Python, Node, FFmpeg and ffprobe are bundled.

## Maintainer build

From the repository root, create a clean Python 3.10+ x64 venv, then:

```powershell
.\.build-env\Scripts\python.exe -m pip install -r packaging\build-requirements.txt
.\packaging\build.ps1
```

Prerequisites: `.build-env`, Inno Setup 6 compiler at
`.build-tools\InnoSetup\ISCC.exe` (or pass `-Iscc`), and redistributable x64
`ffmpeg.exe`, `ffprobe.exe`, `node.exe` under `packaging\vendor` with their license
texts in `vendor\licenses`. Current bundle uses Node 22.22.0. Record versions and
hashes when replacing vendor tools. Do not use an FFmpeg build with `--enable-nonfree`.
Read THIRD-PARTY-NOTICES.md before redistribution; public distribution also needs
the corresponding GPL sources, not just URLs and license texts.

Output: `dist\installer\ClipHarbor-Setup-0.5.0-win-x64.exe`.

Validate the self-contained bundle without developer tools on PATH:

```powershell
.\.build-env\Scripts\python.exe tests\packaged_smoke.py dist\ClipHarbor\ClipHarbor.exe
```

The smoke test uses temporary per-user state and a local HTTP media source; it
tests launch/authentication, duplicate launch, projects, waveform, actual export,
downloader, tools and clean shutdown. It does not modify real projects.

## Updates and user state

Keep the Inno AppId unchanged. Bump runtime.VERSION, HTML asset version strings
and the installer AppVersion together. Quit the app and install the new setup
over the old one. `%LOCALAPPDATA%\ClipHarbor` is outside the installation directory
and survives upgrades and uninstall. The app does not auto-download updates.

For testing, `CLIPHARBOR_DATA_DIR` overrides the data directory and `--no-browser
--port 0` selects an unused port without opening a tab. Normal launches choose
8765, or another free localhost port if it is busy. Named projects persist across
ports; browser drafts are origin-specific, so use Save project for ongoing work.

No signing certificate or publishing destination is configured. The installer is
unsigned and local; there is no public download URL. Windows SmartScreen may warn.
Use a signing certificate and complete third-party-source compliance before a
public release. A separate native build is needed for macOS/Linux.
