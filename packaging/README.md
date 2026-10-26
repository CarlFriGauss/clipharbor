# Building the Windows installer

This is the existing ClipHarbor application, not a rewrite. PyInstaller makes a
windowless one-folder application; Inno Setup wraps it in a per-user installer.
The browser remains the interface. Python and Node are bundled. A graphical
first-run setup fetches FFmpeg/ffprobe directly from the upstream distributor,
checks pinned archive and binary hashes, and installs them in per-user app data.
No terminal is needed. Network access is required for that first launch.

## Maintainer build

From the repository root, create a clean Python 3.10+ x64 venv, then:

```powershell
.\.build-env\Scripts\python.exe -m pip install -r packaging\build-requirements.txt
.\packaging\build.ps1
```

Prerequisites: `.build-env`, Inno Setup 6 compiler at
`.build-tools\InnoSetup\ISCC.exe` (or pass `-Iscc`), and redistributable x64
`node.exe` under `packaging\vendor` with Node and Python license
texts in `vendor\licenses`. Current bundle uses Node 22.22.0. Record versions and
hashes when replacing vendor tools. Do not use an FFmpeg build with `--enable-nonfree`.
Read THIRD-PARTY-NOTICES.md. The spec deliberately excludes FFmpeg binaries;
do not replace the explicit file list with the entire vendor directory.

Outputs: `dist\installer\ClipHarbor-Setup-0.9.3-win-x64.exe`,
`dist\installer\ClipHarbor-Extension-0.9.3.zip`, and
`dist\installer\ClipHarbor-Facebook-Companion-0.9.3.zip`.
The build script reads `mediaforge.runtime.VERSION` and passes it to Inno Setup
so the application and installer versions agree.

The bundle contains a windowless ClipHarbor.exe and a minimal console/stdio
ClipHarborBridge.exe, sharing collected runtime DLLs. The bridge's separate
dependency graph excludes yt-dlp, Flask and Tk; media work runs in the normal
app. The extension is copied from an explicit flat file list (no caches or user
data). Inno Setup registers `com.clipharbor.downloader` per user for Chrome/Edge,
with only the two stable companion origins allowed. The native protocol separates
download/Drive actions from Facebook task actions. The user loads each extension
explicitly; no browser policy or forced extension installation is used.
See [extension setup](../browser-extension/README.md) and
[release notes](RELEASE-0.9.3.md). Store publication is a separate review step.

The Facebook companion is separate because Chrome does not support optional
debugger permission. Its code attaches only to its dedicated Facebook tab, but
that browser permission itself is powerful and not limited to one site. It is
never added to the downloader. Both companion folders use explicit flat file
lists, excluding caches and user state. Google Picker API must be enabled in the
publisher's existing project; native OAuth picker mode uses the existing desktop
registration with drive.file, PKCE and a loopback callback, without an API key.

The build probes a working Tcl/Tk instance and explicitly collects its loaded
DLLs and library scripts as a matched set. Do not rely on DLL discovery through
PATH: another Conda installation may contain a different patch release.
Before Inno Setup runs, the packaged executable must pass the graphical first-run
test with an empty data directory and developer tools removed from PATH.

Validate the self-contained bundle without developer tools on PATH:

```powershell
.\.build-env\Scripts\python.exe tests\packaged_smoke.py dist\ClipHarbor\ClipHarbor.exe --graphical-setup
```

The smoke test uses temporary per-user state and a local HTTP media source; it
tests launch/authentication, duplicate launch, projects, waveform, actual export,
downloader, tools, native bridge download/progress, shared Activity, cold engine
startup and clean shutdown. It does not modify real projects.

## Updates and user state

Keep the Inno AppId unchanged. Bump runtime.VERSION, HTML asset version strings
and the installer AppVersion together. Quit the app and install the new setup
over the old one. `%LOCALAPPDATA%\ClipHarbor` is outside the installation directory
and survives upgrades and uninstall. The app does not auto-download updates.

For testing, `CLIPHARBOR_DATA_DIR` overrides the data directory and `--no-browser
--port 0` selects an unused port without opening a tab. Normal launches choose
8765, or another free localhost port if it is busy. Named projects persist across
ports; browser drafts are origin-specific, so use Save project for ongoing work.

The installer is unsigned; Windows SmartScreen may warn. Do not disable security.
Published builds: https://github.com/CarlFriGauss/clipharbor/releases
A separate native build is needed for macOS/Linux.

## Publisher Google sign-in registration

Configure one OAuth Desktop app client for ClipHarbor in Google Cloud, enable
Drive API and/or YouTube Data API v3, and complete the required consent and
production verification. End users should only click **Sign in with Google**.
They must never create Cloud projects or supply JSON credentials themselves.

The official installer includes the native-app registration; it is excluded
from Git. Source-build publishers configure their own app registration and consent
project. This identifies the app; it is not a user's account authorization.

Before building, put that registration in the ignored root file
`google-oauth-client.json`, or set `CLIPHARBOR_GOOGLE_CLIENT_FILE` to its absolute
path. The spec validates and normalizes the registration, includes only its
client ID and optional desktop client secret, and rejects token-bearing input.
Google treats installed applications as public clients; the desktop registration
cannot be kept confidential inside a distributed app. User authorization is
protected separately by PKCE and the operating system's credential store.

Never bundle `.connections`, user refresh/access tokens, or a developer's signed-in
account. Each user grants access in Google's browser flow and gets their own
protected connection. A build without publisher registration keeps local media
features available and reports Google sign-in unavailable. Live authorization
cannot be tested until a real registered client is supplied.

The ClipHarbor publisher project is `clipharbor`. Its app information and privacy
pages are published at `https://carlfrigauss.github.io/clipharbor/` and
`https://carlfrigauss.github.io/clipharbor/privacy.html`, with source in `docs/`
and a separate `gh-pages` deployment branch. The Google consent configuration is
in production. This is distinct from Google approval of sensitive or restricted
scopes and from YouTube's upload audit; complete those reviews where required.
Do not return released builds to Google's testing mode: refresh tokens issued
in testing expire after seven days. Replace any testing authorization through a
fresh sign-in after switching to production.
