# ClipHarbor 0.5.2 — Windows startup fix

Download **ClipHarbor-Setup-0.5.2-win-x64.exe** below. Close ClipHarbor and any
startup error dialog, then run this installer over your existing installation.
There is no need to uninstall or delete projects, media, or settings.

This release fixes the first-launch "Can't find a usable init.tcl" error in
0.5.1. That build mixed Tcl/Tk 8.6.14 DLLs with 8.6.13 startup scripts. The build
now selects the DLLs and scripts from the same initialized runtime, and must pass
a real graphical first-run setup test before producing an installer.

- Windows 10/11 x64; unsigned, so Windows may show a publisher warning.
- No terminal or manual runtime installation needed.
- Stay online for first-time automatic media-tool setup. Local editing works
  offline afterward. Use **Quit app** when finished.
- Saved projects/cache remain in `%LOCALAPPDATA%\ClipHarbor`; upgrades preserve them.
- `SHA256SUMS.txt` verifies the release files. The third-party source archive
  contains exact source distributions for the bundled components listed in notices.

Only download and edit media you have permission to use. Do not disable Windows
security to run this app.
