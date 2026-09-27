# ClipHarbor

ClipHarbor is a local, browser-based media downloader and non-destructive editor powered by `yt-dlp`, `ffprobe`, and `ffmpeg`.

It is designed around a workflow rather than a collection of scripts:

1. Inspect a public media URL and show what was found.
2. Download the best available source streams. MP4 is the default final output and does not require opening the editor or exporting again.
3. Keep the source container untouched or deliberately output MP4, MKV, WebM, MOV, MP3, M4A, or WAV.
4. For MP4 video, optionally request **X compatibility**. ClipHarbor probes the completed file and skips conversion when it already meets the compatibility profile.
5. Send the completed file straight into a fresh timeline project, with the media already placed on the first compatible layer.
6. Build a non-destructive edit from video and audio clips, split clips into independently editable sections, and render the result with FFmpeg.

## Requirements

- Windows 10/11 x64 for the installer; source setup instructions below also cover macOS and Linux (not yet tested on those operating systems)
- Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH`
- Node.js 22+ on `PATH` for YouTube JavaScript challenges
- Python dependencies are installed by the commands below

## Start

### Windows installer

[Download ClipHarbor for Windows](https://github.com/CarlFriGauss/clipharbor/releases/latest)
— open the release and download `ClipHarbor-Setup-0.5.1-win-x64.exe`.
Run the installer, then open **ClipHarbor** from the desktop or Start menu.
No terminal or separate runtime setup is needed. On first launch, a setup window
downloads and verifies the media tools; stay online until it finishes. The app
then opens in your browser. Use **Quit app** when finished. Later local editing
works offline. Windows 10/11 x64 only; macOS/Linux users should use source setup.
Do not use GitHub's automatic "Source code" ZIP as an installer.

Installed projects, cache and logs use `%LOCALAPPDATA%\ClipHarbor`; updates and
uninstall leave those files intact. To update, quit and run a newer installer.
This build is unsigned; Windows may show a publisher warning. Do not disable
Windows security. Download only from this repository's releases. See
[packaging notes](packaging/README.md) for build, testing and release requirements.

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
