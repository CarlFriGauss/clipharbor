# ClipHarbor

ClipHarbor is a local, browser-based media downloader and non-destructive editor powered by `yt-dlp`, `ffprobe`, and `ffmpeg`.

**Get started:** [Download the Windows installer](https://github.com/CarlFriGauss/clipharbor/releases/download/v0.8.0/ClipHarbor-Setup-0.8.0-win-x64.exe)
— no terminal needed. Or use the [automatic terminal setup](#zero-prerequisite-terminal-install)
for Windows, macOS, or Linux; it installs missing components for you.

It is designed around a workflow rather than a collection of scripts:

1. Inspect a public media URL and show what was found.
2. Download the best available source streams. MP4 is the default final output and does not require opening the editor or exporting again.
3. Keep the source container untouched or deliberately output MP4, MKV, WebM, MOV, MP3, M4A, or WAV.
4. For MP4 video, optionally request **X compatibility**. ClipHarbor probes the completed file and skips conversion when it already meets the compatibility profile.
5. Send the completed file straight into a fresh timeline project, with the media already placed on the first compatible layer.
6. Build a non-destructive edit from video and audio clips, split clips into independently editable sections, and render the result with FFmpeg.
7. Choose **Google Drive** in Download to save space locally, or use **Export** for Drive, YouTube, X, or Facebook. Facebook personal profiles finish posting in the browser; Pages support direct upload. Each destination shows its logo.
8. Download from the page you are watching with the optional **Chrome/Edge browser extension**. The app starts quietly when needed; the extension offers format, computer/Drive destination, and progress without copying URLs.

## Requirements for manual source setup

- Windows 10/11 x64 for the installer; source setup also supports macOS and Linux
- Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH`
- Node.js 22+ on `PATH` for YouTube JavaScript challenges
- Python dependencies are installed by the commands below

These are **not prerequisites you need to install yourself** when using the
installer or automatic terminal setup.

## Start

### Windows installer

[Download ClipHarbor for Windows](https://github.com/CarlFriGauss/clipharbor/releases/download/v0.8.0/ClipHarbor-Setup-0.8.0-win-x64.exe)
— or browse [all releases](https://github.com/CarlFriGauss/clipharbor/releases).
Run the installer, then open **ClipHarbor** from the desktop or Start menu.
No terminal or separate runtime setup is needed. On first launch, a setup window
downloads and verifies the media tools; stay online until it finishes. The app
then opens in your browser. Use **Quit app** when finished. Later local editing
works offline. Windows 10/11 x64 only; macOS/Linux users should use source setup.
Do not use GitHub's automatic "Source code" ZIP as an installer.

Version **0.8.0** adds visual Google Drive destination selection and an optional
Facebook posting companion. It also includes the [browser extension](#browser-extension) for
Chrome and Edge, with background downloads to this computer or Google Drive.
The installer registers its small local bridge and includes the extension files.
Loading the extension in your browser is a one-time manual step.
Facebook personal-profile export prepares your video and opens Facebook to finish
posting there. The editor includes resizable Media, preview, Properties, and
timeline areas. The preview always fits the entire frame. A folder button toggles
Media; Properties follows source files, timeline sections, and selected layers.
Direct Google Drive downloads and cloud/social export remain included.
For Drive, click **Sign in with Google** once; Download and Export share the same
protected connection and dedicated folder. No Google Drive desktop installation,
credentials file, or developer setup is needed in the Windows installer.
YouTube requires its own Google upload permission. X and Facebook Page publishing
require the platform tokens described below. Personal-profile sharing needs no
Facebook token in ClipHarbor. Each installer user signs in to their own account.
Advanced source builds need the publisher registration described below.
[Release notes](packaging/RELEASE-0.8.0.md)
explain the supported destinations and validation. The earlier Tcl/Tk startup
fix remains included; install over the old version without deleting projects.

Installed projects, cache and logs use `%LOCALAPPDATA%\ClipHarbor`; updates and
uninstall leave those files intact. To update, quit and run a newer installer.
This build is unsigned; Windows may show a publisher warning. Do not disable
Windows security. Download only from this repository's releases. See
[packaging notes](packaging/README.md) for build, testing and release requirements.

### Browser extension

1. Install **ClipHarbor 0.8.0 or newer** and open it once to finish media-tool setup.
2. Open `chrome://extensions` in Chrome or `edge://extensions` in Edge.
3. Enable **Developer mode**, click **Load unpacked**, and select
   `%LOCALAPPDATA%\Programs\ClipHarbor\browser-extension` (inside your installation).
   Alternatively, download [ClipHarbor-Extension-0.8.0.zip](https://github.com/CarlFriGauss/clipharbor/releases/download/v0.8.0/ClipHarbor-Extension-0.8.0.zip),
   extract it to a permanent folder, and select that folder.
4. Pin ClipHarbor to your browser toolbar. Open a video page, click ClipHarbor,
   choose the link, format and **This computer** or **Google Drive**, and download.

This GitHub release is **not listed in the Chrome Web Store or Edge Add-ons**.
The browser installation is explicit; ClipHarbor never force-installs extensions
or changes browser security policies. The stable ID for this build is
`nopjlekidanihaoahnpcnkacdpgljejl`. Chrome/Edge 120+ on desktop are supported.

You can also right-click a video, link or page and choose **Download with
ClipHarbor**. This uses your last successful extension request's format and
destination. For a feed containing several videos, choose the intended video in
the popup or paste its individual permalink. Some sites expose no usable link;
the downloader's existing source/authentication/DRM limits still apply.

The desktop engine starts quietly if needed. Downloads continue after you close
the popup. The badge shows running downloads; reopen the popup for progress,
**Open folder**, or **View in Google Drive**. **Open app** opens Activity, where
extension downloads can also be edited or exported. Recent jobs are held by the
running engine and may be lost after a crash/restart; failed status checks never
silently submit a second download. Use **Quit app** when finished.

Drive uses the same operating-system-protected account connection and dedicated
folder as Download and Export. **Connect in ClipHarbor** opens the existing
Google sign-in; reopen the popup after connecting. The extension never receives
Google tokens or the local desktop session secret. It requests temporary access
to the page you invoke, not access to every site, browser cookies, passwords or
general browsing history. There is no analytics or cloud processing service.
Browser storage keeps recent download IDs, progress and output locations.

**Source users:** install the usual source prerequisites, then run
`python browser-extension/register_host.py` using that Python environment and
load the repository's `browser-extension` folder. The bridge starts the source
desktop engine on demand. Keep the checkout and environment in place.
`python browser-extension/register_host.py --unregister` removes matching source
registrations without deleting media or connections. Source and installer
registrations share a name; the most recent setup wins. Re-run the installer to
switch back to its bridge. Unix registration paths are provided; live Windows
validation is the release target. See the [extension guide](browser-extension/README.md).

### Choose a Google Drive folder

In Download or Export choose **Google Drive → Choose Drive folder…**. Google opens
its own folder browser. Select a folder you can upload into; ClipHarbor verifies
it and remembers it for Download, Export, and the downloader extension. The
extension has its own **Choose folder…** button. Folder selection requests only
`drive.file` access to folders explicitly selected through Google’s picker.
Normal uploads reuse the remembered connection and do not reopen the picker.

Cancelling, choosing a non-folder, or selecting a read-only folder keeps the
previous connection and default. Each queued upload snapshots its destination;
changing the default while another job runs does not redirect that job. Existing
manual folder-ID setup remains available under Advanced and can require broader
Drive access. A publisher must enable **Google Picker API** once in the same
Google Cloud project; no API key or extra setup is needed by installer users.

### Facebook browser posting

For an automatic **video + caption → Facebook post** workflow on your own
profile, this release includes a separate, optional **ClipHarbor Post** browser
companion. This is experimental automation of Facebook’s website, not an official
personal-profile publishing API. The normal downloader extension gains no
Facebook host or debugger permission.

1. In Chrome/Edge’s Extensions page load the installed
   `%LOCALAPPDATA%\Programs\ClipHarbor\facebook-extension` folder, or extract
   `ClipHarbor-Facebook-Companion-0.8.0.zip` from the release and load that folder.
2. Review its stronger **debugger** permission. Chrome does not allow this
   permission to be requested optionally. Although this companion’s code attaches
   only to the Facebook tab it creates, the browser permission itself is powerful
   and is not technically limited to one site. Installing this companion is optional.
3. Open your own Facebook profile, with **Edit profile** visible. Click the
   **ClipHarbor Post** icon and **Connect this Facebook profile** once.
4. In Export choose **Facebook → My profile · post through browser companion**,
   enter your caption and audience, and click **Post video to Facebook** or
   **Render & post to Facebook**. The audience starts at **Only me**.

Keep the connected browser open. It checks for export tasks about every 30
seconds, opens the connected profile, attaches the local MP4 through Chrome’s
file input, fills the caption, verifies the requested audience and posts. Chrome
shows a debugging banner while it works. The file is not encoded into large
messages or loaded into extension memory; media rendering stays in the desktop
engine. Facebook handles browser sign-in. No password or cookie is copied.

An existing draft/attachment, login/security check, changed or unrecognized
Facebook controls, unavailable audience, or lost connection stops the task. Your
local file is kept and the default Facebook audience is not changed. Once a Post
click was attempted, a missing confirmation is **uncertain**, not a confirmed
failure. Check Facebook before starting another export; the companion does not
resubmit automatically and Activity removes its ordinary Retry button in that
case. English desktop Facebook is the primary validation target; other layouts
and languages may need adapter updates. The manual handoff and official advanced
Page API remain available separately. See [the companion guide](facebook-extension/setup.html).

### Windows / PowerShell

The commands below are the **manual source setup** for people who already have
development tools. For automatic setup, see [zero-prerequisite terminal install](#zero-prerequisite-terminal-install).

Install [Python](https://www.python.org/downloads/) 3.10+, [Git](https://git-scm.com/downloads),
[FFmpeg](https://ffmpeg.org/download.html) (including ffprobe), and
[Node.js](https://nodejs.org/en/download) 22+. Ensure their commands are on PATH,
then open a new PowerShell window:

```powershell
git clone https://github.com/CarlFriGauss/clipharbor.git
cd clipharbor
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py --open
```

For subsequent starts, run the last command from the `clipharbor` directory.
No PowerShell execution-policy changes or environment activation are required.
Alternatively, `run.ps1` uses an active Conda environment or creates `.venv`;
pass `-Python <path-to-python.exe>` to select another interpreter.

Normal launches skip pip when the required packages are already installed, so startup remains quick and works without a network check. Because media sites change frequently, update yt-dlp and the other dependencies when a downloader extractor stops working:

```powershell
.\run.ps1 -UpdateDependencies
```

### macOS / Terminal

With [Homebrew](https://brew.sh/) installed:

```sh
brew install python git ffmpeg node python-tk
git clone https://github.com/CarlFriGauss/clipharbor.git
cd clipharbor
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py --open
```

### Linux / bash (Ubuntu or Debian)

Install Python 3.10 or newer, FFmpeg, and Tk using your distribution's packages.
Install Node.js 22+ following the [Node.js instructions](https://nodejs.org/en/download)
if your distribution's Node version is older.

```sh
sudo apt update
sudo apt install git python3 python3-venv python3-tk ffmpeg
git clone https://github.com/CarlFriGauss/clipharbor.git
cd clipharbor
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py --open
```

For subsequent macOS/Linux starts, run the last command from `clipharbor`.
If the browser does not open, visit http://127.0.0.1:8765. Stop the source server
with Ctrl+C in its terminal. Keep it on localhost; do not expose it to the internet.
Source mode uses the Flask development server, not a hosted multi-user service.

### Updates and development

Quit the app before updating. Run `git pull --ff-only`, then repeat the appropriate
Python `-m pip install -U -r requirements.txt` command. Saved projects and cached
media are ignored by Git and stay local. Back up projects and original media yourself.

This is a Python application, not an npm package. npm is not required and would
not remove the underlying runtime requirements. The automatic setup below handles
those requirements for you without needing npm.

Run the regression tests from an environment with FFmpeg on PATH:

```powershell
python -m pip install -r requirements.txt pytest
python -m pytest -q
node tests/timeline_regressions.cjs
node tests/extension_regressions.mjs
node tests/facebook_companion_regressions.mjs
node tests/facebook_page_regressions.mjs
```

## Zero-prerequisite terminal install

**Open a terminal, paste the block for your computer, and wait for the browser to
open. You do not need to install any development tools first.** First setup needs
internet and may take several minutes. Run the same block again to reopen the app;
working components are reused. Keep the terminal open while using ClipHarbor,
then press Ctrl+C in it when finished.

These commands download and run this repository's setup script. Only run them if
you trust this repository; the scripts are available to inspect as
[run.ps1](run.ps1) and [run.sh](run.sh). They install Git if needed, obtain the app,
set up its missing components in your user account, and launch it. They do not
change your shell profile or system-wide PATH, and do not overwrite an existing
checkout with unrelated contents. No administrator access is needed for normal
setup. The Linux fallback below may ask for your password to install a missing
download utility; all remaining setup is user-local.

### Windows — automatic setup

Open **PowerShell** and paste:

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$setup = (Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/CarlFriGauss/clipharbor/main/run.ps1').Content
& ([scriptblock]::Create($setup)) -InstallRepository
```

Windows 10/11 x64. No permanent execution-policy change is needed.

### macOS — automatic setup

Open **Terminal** and paste (Intel and Apple Silicon):

```sh
setup_file=$(mktemp)
curl -fL --retry 3 https://raw.githubusercontent.com/CarlFriGauss/clipharbor/main/run.sh -o "$setup_file" && bash "$setup_file" --install
```

### Linux — automatic setup

Open a terminal and paste. Supports glibc-based desktop distributions on x64 or
ARM64; Alpine/musl is not supported by this automatic path. The app needs a
desktop/browser for its normal interface.

```sh
(
  set -e
  if ! command -v curl >/dev/null && ! command -v wget >/dev/null; then
    echo 'Installing a download helper; your system may ask for your password.'
    if command -v apt-get >/dev/null; then sudo apt-get update && sudo apt-get install -y curl ca-certificates
    elif command -v dnf >/dev/null; then sudo dnf install -y curl ca-certificates
    elif command -v pacman >/dev/null; then sudo pacman -S --needed curl ca-certificates
    elif command -v zypper >/dev/null; then sudo zypper install -y curl ca-certificates
    else echo 'Install curl using your system package manager, then rerun this block.'; exit 1; fi
  fi
  setup_file=$(mktemp)
  if command -v curl >/dev/null; then curl -fL --retry 3 https://raw.githubusercontent.com/CarlFriGauss/clipharbor/main/run.sh -o "$setup_file"
  else wget -O "$setup_file" https://raw.githubusercontent.com/CarlFriGauss/clipharbor/main/run.sh; fi
  bash "$setup_file" --install
)
```

### Already downloaded the repository?

Run `./run.ps1` in PowerShell, or `bash ./run.sh` on macOS/Linux. These also check
for missing tools and install them; they are not just launch shortcuts.

Automatic setup uses a checksum-pinned [Micromamba](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html)
helper and only the conda-forge channel for missing Git, runtime, media tools, or
JavaScript runtime. App packages live in the checkout's `.venv`. System tools
that pass checks are reused; the managed installation is only for missing or
unusable components. Nothing is installed into your system Python or existing
Conda environment. Package installations may pull in their own dependencies.

Storage: `%LOCALAPPDATA%\ClipHarbor\bootstrap` on Windows;
`${XDG_DATA_HOME:-~/.local/share}/clipharbor/bootstrap` on macOS/Linux. The cloned
app and its source-mode projects are under `source` there. Do not delete that
folder without backing up saved projects. `CLIPHARBOR_BOOTSTRAP_DIR` can override
the location. Installer projects and source-mode projects are separate.

Rerunning setup does not silently update or discard your source changes. To update
the app, use `git pull --ff-only` in its checkout. To refresh download support,
run `./run.ps1 -UpdateDependencies` or `bash ./run.sh --update-dependencies`.
Maintainers can use `-SetupOnly` / `--setup-only` to verify setup without launching.

Automated [cross-platform checks](https://github.com/CarlFriGauss/clipharbor/actions/workflows/bootstrap.yml)
cover missing-tool setup, repeat setup, app startup, waveform generation, and MP4
export on Windows, Ubuntu, and macOS. These are smoke tests, not exhaustive
verification of every editing operation or website.

## Editor model

The workspace fits the browser window. Drag the divider between preview and timeline to give either panel more room. The time ruler stays pinned while scrolling through tracks, and track names stay pinned while scrolling through time. New projects start with one video and one audio track; use V+ / A+ to add more. Empty layers are tucked away once clips are added; enable **Empty layers** to show them. Adding a layer also reveals them.

Click a clip or the ruler to place the cursor, or type an exact `HH:MM:SS.mmm` position in the transport field. Arrow keys in that field step by 0.01 seconds (Shift: one second). Both scissors buttons and `S` cut at this exact timeline position, independently of silence, snapping, or a source preview's playback position. Native media controls are reserved for auditioning sources; timeline clips use the shared transport.

Waveforms draw only the visible range and fetch finer peak samples as you zoom. The backend streams the audio instead of loading a complete long recording into memory, preserves stereo energy, and provides explicit time intervals for waveform bins. Export shows the expected timeline duration and verifies the finished file, allowing only codec/frame padding rather than seconds of discrepancy.

### Accurate MP3 seeking (v0.4.2)

Long variable-bitrate MP3s can mislead a browser's approximate seek table: `currentTime` may look correct while the sound is tens of seconds away. ClipHarbor now copies MP3 packets into a precisely indexed MP4 container on first use. There is **no audio re-encoding** in this preparation. Playback, waveform extraction and editor export use that same index. A short decoder preroll is discarded before extracting waveform windows or rendering cuts, preserving audio at the start of a section.

The reusable cache is under `.cache/audio-index-v1` inside the app folder; it uses roughly the original MP3's disk space, not a multi-gigabyte decoded audio buffer in memory. The interface shows “Preparing precise audio…” during first use. After closing the app, this cache folder can be removed to reclaim space; it will be rebuilt as needed. Originals and saved projects are unaffected. Source changes invalidate the cached copy automatically.

Old projects retain their numeric cut positions. Please listen again around cuts made with the old MP3 preview: the app cannot infer which words you intended to include. It does not silently shift existing edits or overwrite earlier exports. The internal `mediaforge` module, saved-project format and browser-storage keys are retained for compatibility after the ClipHarbor rename.

The editor never changes source files. Editing is section-based:

1. Put a source on a video or audio layer.
2. Seek to an exact moment in the player.
3. Click the scissors button (or press `S`). One cut creates two sections; `n` cuts create `n + 1` independently selectable sections.
4. Click a section to act on it. Ctrl-click selects unrelated sections; Shift-click selects a range on one layer.
5. Click a layer header (`V1`, `V2`, `A1`, and so on) to select that layer. Ctrl-click additional headers to select several layers. Cutting then splits every selected layer that has media at the playhead.
6. Copy, paste, remove, ripple-delete, mute, change volume, or change speed. Inspector changes apply to the full multi-selection.
7. Drag sections left/right in time or vertically between compatible layers. The magnet snaps section edges to time zero and neighboring section edges, making it easy to join media without gaps.

Useful shortcuts are `Space` for play/pause, `S` for scissors, `Delete` to remove, `Ctrl+C`/`Ctrl+V` to copy/paste, `Ctrl+Z`/`Ctrl+Y` for undo/redo, and `Ctrl+A` to select all sections.

Every timeline section stores:

- source in/out points;
- position on the timeline;
- playback speed from 0.25x to 4x (FFmpeg `atempo` chains preserve audio pitch);
- volume or mute state;
- video layer and fit mode.

Layer controls provide visibility, mute, and lock states. Add audio sources for music, voice-over, or effects. Video sections may be connected one after another or stacked on higher layers. Undo/redo and optional ripple deletion make structural edits recoverable. Every audio-bearing section—including a video clip's embedded audio—displays a cached peak waveform, and timeline playback mixes every audible video/audio section while keeping the visible video synchronized to the same playhead. Audio auto-balance (the scale button) is enabled by default: added audio is smoothly ducked under active video sound, all tracks pass through one shared Web Audio mixer, and master peak protection prevents digital clipping. Disable the scale button when deliberately mixing only with the section volume controls. The FFmpeg export applies the same balancing and peak protection.

The editor has Media on the left, an uncropped preview in the center, Properties
on the right, and a timeline across the full bottom width. Drag either vertical
divider or the horizontal timeline divider to resize the workspace. Click the
folder icon to hide or restore Media; yellow means open. Panel sizes and the
Media toggle are remembered on this browser. The preview fits the entire frame
for portrait and landscape video, including while resizing. Fullscreen is a
separate button; when native browser fullscreen is unavailable, the preview
expands inside the browser window. Escape or the exit button restores the editor.

Properties shows file details for a Media selection, editable section settings
for a timeline selection, and layer controls for selected layer labels (V1, A1,
and so on). Even an empty layer has its own properties. Multiple selected sections
retain common-value and mixed-value editing. Hiding Media does not change the
selection or its Properties.

Cuts do not create playback discontinuities. Adjacent sections on the same layer that touch in both timeline time and source time share one uninterrupted preview chain. Crossing their cut edge changes the independently editable section state without recreating a media player or seeking back to a keyframe.

Normal playback never performs backward corrective seeks. Small clock differences are corrected by imperceptibly varying the non-master playback rate within a narrow range, and the timeline clock is monotonic. Explicit seeks are reserved for user actions such as scrubbing or intentionally jumping to a non-contiguous source section.

The editor has an explicit project lifecycle. **New** starts a clean workspace, **Save project** stores a named project under the local `projects/` directory, and **Open** lists saved work so it can be continued on another day. The current workspace is also kept as a browser recovery draft for reload/crash recovery, but it is not confused with a newly downloaded file: choosing **Edit this media** always creates a fresh project and places that result on the timeline automatically. Export can optionally write a portable `.mediaforge.json` project description beside the output file; this option is off by default.

Media in the project library has its own remove control. Removing unused media only removes its project reference. If the media is already used on the timeline, ClipHarbor confirms before removing its sections as well. The source file itself is never deleted.

The browser player previews the selected clip with its trim, speed, and volume settings. The logarithmic timeline zoom ranges from a whole-project overview to fine-grained cuts, with a dedicated Fit control. Final composition—including multiple sources and audio mixing—is produced by FFmpeg. Render inputs are accurately pre-seeked to each section before decoding, which avoids repeatedly decoding unused portions of long source files. FFmpeg's machine-readable progress feed drives the Activity percentage.

After an inspected source reports multiple audio tracks, the downloader shows an **Audio track** menu. It distinguishes the original/default track from dubbed and descriptive tracks and downloads the best stream belonging to the exact selection. YouTube only exposes this menu when that specific video actually offers multiple tracks. See [YouTube's automatic dubbing help](https://support.google.com/youtube/answer/15569972?hl=en) and [yt-dlp format selection](https://github.com/yt-dlp/yt-dlp#format-selection).

Completed downloads and renders remain actionable in **Activity**: their exact output path is shown, **Open folder** reveals the destination, and **Edit as new project** remains available after the completion dialog is dismissed.

## Privacy and authenticated sites

ClipHarbor does not use browser cookies by default. Public media works without them. If a site requires login, use an exported Netscape cookies file from a disposable/low-risk account and treat that file like a password. The app is intentionally bound to `127.0.0.1` only.

Only download media you have the right to access and save. Sites may change their extractors and terms over time; keep `yt-dlp` current.

Both the downloader and editor export offer explicit X compatibility. In the editor, choose **X compatible MP4 · highest quality**; canvas, frame rate, and quality controls are then automatic. ClipHarbor keeps the largest source-based resolution allowed by the profile, uses up to 40 FPS, H.264 High with yuv420p, AAC-LC stereo, fast-start MP4, and a bitrate ceiling below the 25 Mbps web-upload limit. It probes the finished render and reports success only after compatibility validation. Duration and file-size allowances depend on the account tier; ClipHarbor reports those separately rather than trimming content without permission. See [X's current video guidance](https://help.x.com/en/using-x/x-videos).

## Project layout

```text
app.py                  Local server entry point
mediaforge/downloader.py yt-dlp inspection and background downloads
mediaforge/ffmpeg.py     probing, conversions, and X compatibility
mediaforge/editor.py     timeline validation and FFmpeg render graph
mediaforge/jobs.py       background job state and progress
mediaforge/waveform.py   cached audio peak extraction
mediaforge/web.py        local API and media streaming
static/                  application interface
tests/                   command-generation and compatibility tests
```

## Download directly to Google Drive

In the Downloader's **Output** card, use the icons under **Save to** to choose
**This computer** or **Google Drive**. The computer option uses the output folder
as before. Drive uses the same Google connection and remembered destination folder
as Export; connecting or disconnecting in either place applies to both.

Cloud downloads use isolated temporary disk space for yt-dlp and FFmpeg, then
upload the finished file in chunks. After Drive confirms the file size and folder,
ClipHarbor removes the temporary source, output, and partial files. No permanent
local copy is kept. All supported download formats, including original containers
and audio-only files, can go to Drive. Activity and the completion dialog show an
**Open in Google Drive** link. Download to **This computer** when you need local
media for editing.

If an upload fails, Activity offers **Retry upload** without downloading or
converting again, and **Discard temporary download** to free disk space. Pending
uploads are recovered after a page reload or app restart. An interrupted source
download can also be discarded. If cleanup encounters a locked file after a
successful upload, use **Remove temporary files**; the completed upload is recorded
so it is not uploaded again.

Run the cloud download regression checks with:

    python -m pytest -q tests/test_cloud_downloads.py

Provider responses in these tests are simulated; live Google sign-in and uploads
require the app's Google OAuth registration and an authorized account.

## Export to Google Drive and social platforms

The Export dialog includes local saving, Google Drive, YouTube, X, and Facebook
Pages, with local SVG logos. Finished downloads also have **Export / share**,
so an existing MP4 can upload directly without another render. A local copy is
retained. Activity shows upload progress, remote links, errors, and **Retry upload**
for a failed delivery. Failed uploads never require rendering the timeline again.

These optional integrations use Python's standard library, bounded 4 MiB upload
chunks or streaming, and the existing background jobs. They add no runtime
dependencies, GPU requirement, third-party JavaScript, or always-running service.
A video render still uses the existing FFmpeg pipeline.

### One-time connections

Users click **Sign in with Google** and authorize ClipHarbor in their browser.
They never select a credentials file or enter a Google password into ClipHarbor.
The same Drive connection is shared by Download and Export, survives app restarts,
and renews short-lived access tokens automatically. Sign-in is requested again
when Google authorization expires or is revoked. A network failure preserves the
saved authorization for a later retry.

The official installer includes ClipHarbor's Google OAuth **Desktop app**
registration. Each user connects their own Drive or YouTube account. No publisher
account or user token is included. Google permissions, verification rules, and
account limits still apply. The registration is excluded from Git; source builds
need a publisher-supplied registration before Google sign-in is available.

Source-build publishers register their own Desktop app, enable the relevant APIs,
and configure consent and production verification. Supply the registration
through `CLIPHARBOR_GOOGLE_CLIENT_FILE`, or put an ignored
`google-oauth-client.json` at the resource root before building. The installer spec
embeds only that publisher registration under a normalized file name. Source builds may alternatively
set `CLIPHARBOR_GOOGLE_CLIENT_ID` and `CLIPHARBOR_GOOGLE_CLIENT_SECRET`. These
identify the app; they are separate from every user's authorization. Desktop
client registrations cannot be treated as confidential secrets in a distributed
application; PKCE protects the authorization exchange. Never bundle user tokens.
A build without registration reports that Google sign-in is unavailable; it does
not make ordinary users create Cloud projects.

Publisher app information and the privacy policy are available at
[the ClipHarbor website](https://carlfrigauss.github.io/clipharbor/) and
[Privacy policy](https://carlfrigauss.github.io/clipharbor/privacy.html).
Their source lives in `docs/`; the documentation site uses a separate `gh-pages`
branch and adds no application dependencies. Keep the Cloud consent configuration
in production for released builds: Google's testing mode issues refresh tokens
that expire after seven days. An authorization created during testing must be
renewed after moving to production; existing account revocation and expiry rules
still apply.

Drive defaults to the limited **drive.file** scope and creates and remembers a
**ClipHarbor Exports** folder on its first upload. Prefer **Choose Drive folder**
to select an existing folder with limited access. Advanced manual folder IDs
are still supported: enter an ID before connecting. That connection requests the broader **drive**
scope through Google's consent screen so it can access the selected folder.
Changing to another existing folder may require reconnecting. The selected folder
is remembered. Drive upload success requires reading back the file size and parent.

YouTube requires a channel and defaults to **Private**. Choose Private, Unlisted,
or Public in Export; ClipHarbor uploads the video, title and description directly
through YouTube's API. Google's API quotas, authorization requirements and channel
restrictions apply. Google's current [upload documentation](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert)
states that unverified API projects are not automatically restricted to private
uploads. YouTube may continue processing after accepting the file. Sign-in and
upload authorization were verified; successful live upload testing remains
deferred until the test channel's temporary restriction ends.

X requires a **user** access token with media.write, tweet.write, tweet.read, and
users.read permissions plus developer API access for uploads and posts.
App-only bearer tokens are insufficient. Export requires an explicit **Publish
this video as an X post** selection, waits for media processing, and then creates
the post. Token expiry requires reconnecting. Platform access/usage charges and
account-specific media limits apply.

For a **personal Facebook profile**, choose **Facebook → Personal profile**.
ClipHarbor prepares an MP4 and opens Facebook in your default browser. Click
**Copy video location**, choose **Photo/video** in Facebook, and paste the location
into its file picker. **Copy post text** copies your optional caption. Choose
your audience and finish posting in Facebook. Existing MP4 downloads need no
additional render. If the browser cannot open automatically, use **Open Facebook**
in the completion dialog. Activity's **Continue in Facebook** reopens the file
instructions. ClipHarbor reports the video as ready, never as already posted.

Meta does not allow direct app publishing to personal profiles; its Share Dialog
shares links rather than attaching a local video. Facebook sign-in stays in your
browser, and ClipHarbor does not request or save a Facebook password or token for
this workflow. See [Meta's sharing documentation](https://developers.facebook.com/documentation/sharing/reference/share-dialog).

For a **Facebook Page**, choose **Page I manage · finish in Facebook** and switch
to your Page in Facebook before attaching the video. This needs no developer
configuration. For direct API uploads instead, choose **Page · direct API upload
(advanced)**. Connect a Page ID
and a Page access token granted by a person allowed to create content on that
Page, with pages_manage_posts and pages_read_engagement permissions
(pages_show_list is also needed when obtaining the Page token). Exports default
to unpublished; explicitly select publishing to make the Page video public.
Meta's app review, token expiry, account permissions, and processing rules apply.

Social exports require MP4 video. Choosing X selects the existing X-compatible
render preset. Sharing an already-downloaded file uploads it unchanged; choose
an appropriate MP4 or render an X-compatible version first.

User tokens are stored separately from projects and browser storage. Windows
uses user-bound DPAPI encryption, macOS uses Keychain, and Linux uses Secret
Service (`secret-tool` from libsecret). There is no plaintext fallback when the
OS credential store is unavailable. A legacy unencrypted source-mode file on
macOS/Linux is removed only after migration to the OS vault is verified.

The connection API returns only status and folder preferences, never passwords,
access tokens, refresh tokens, or client secrets. Bearer authorization is omitted
from redirected requests. Concurrent Download and Export jobs serialize renewal
so they reuse the same refreshed authorization.

**Disconnect** removes the shared local connection and attempts to revoke the
Google grant. If Google cannot be reached, local tokens are still removed and
the UI explains how to revoke the grant in the Google account. Google revocation
invalidates all scopes for the same Cloud project, so related Drive and YouTube
connections are cleared together. Disconnecting while sign-in is open prevents
that unfinished sign-in from silently recreating the saved connection.

### Cloud export checks

Run the existing regression suite and the adapter/security tests:

    python -m pytest -q
    node tests/timeline_regressions.cjs

The publishing tests cover chunk recovery, processing failures, saved-folder
reuse, credential protection, preflight validation, origin checks, and preserving
a failed export for retry. They mock provider responses and do not establish that
a real account has permission to upload. Live Drive, YouTube, X, and Facebook Page
API tests require the relevant platform configuration and each user's authorization.

Release validation also exercised a real Drive sign-in, export upload, direct
Drive download, shared connection after restart, and automatic Google token
renewal. The uploaded file's size and folder were verified, and the direct
download removed its temporary local files. YouTube, X, and Facebook Page publishing
have adapter tests. The manual Facebook handoff was tested with a generated
three-second video and a successful **Only me** post. The new Drive folder picker
and automatic Facebook companion still need live account validation. Direct Facebook
Page API publishing and X still need real-account validation. YouTube sign-in
and upload permission were verified; its live upload test is deferred while the
test account has a temporary posting restriction.
