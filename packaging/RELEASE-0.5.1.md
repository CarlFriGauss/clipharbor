# ClipHarbor 0.5.1 — Windows desktop preview

> Known first-launch defect: this build can fail with a Tcl/Tk `init.tcl`
> version mismatch. Do not use it for a new installation. Use version 0.5.2
> or newer from the Releases page instead.

Download **ClipHarbor-Setup-0.5.1-win-x64.exe** below. Install it and launch
ClipHarbor from the desktop or Start menu. No terminal commands are needed.

- Windows 10/11 x64. This is not a macOS or Linux installer.
- First launch needs internet: a setup window downloads verified media tools
  directly from the upstream distributor. Later local editing works offline.
- The same local downloader/editor opens in your browser. Use **Quit app** to
  close the background application; closing the tab alone leaves it running.
- Save projects before quitting. Projects/cache/logs stay in
  `%LOCALAPPDATA%\ClipHarbor`; installing updates does not remove them.
- Unsigned community build: Windows may show a publisher warning. Do not disable
  Windows security. Check `SHA256SUMS.txt` if you want to verify the downloaded file.
- No automatic updater. To update, quit and install a newer release.

This initial desktop release has been smoke-tested on Windows with developer
tools removed from PATH, including first-run setup, projects, waveform, audio
export, local-URL download and clean shutdown. Website support varies and may
require future downloader updates. Only download media you have permission to save.

The automatic GitHub source archives are for developers, not installers.
