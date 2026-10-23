# ClipHarbor 0.6.0 — Google Drive and export destinations

Download **ClipHarbor-Setup-0.6.0-win-x64.exe** below, close ClipHarbor, and run
the installer over your existing installation. Projects and media are preserved.
Windows 10/11 x64; no terminal or separate Python/Node installation is required.
Stay online for the first launch's verified media-tool setup.

## What's new

- **Download directly to Google Drive**, with its logo beside the computer
  destination. Temporary files are removed after the upload is verified. A failed
  upload can be retried from Activity without downloading the source again.
- **Export destinations with logos:** This computer, Google Drive, YouTube, X,
  and Facebook Pages. Upload a completed download without another render, or
  render an edit and upload it. Failed delivery keeps a local file for retry.
- **One Drive sign-in for Download and Export.** Sign in in Google's browser
  screen; the connection survives restarts and refreshes automatically. Windows
  protects the saved authorization with your Windows account. ClipHarbor never
  receives your Google password. No Google Drive desktop app or JSON setup is
  required. A dedicated **ClipHarbor Exports** folder is created and remembered.
- Streaming and bounded upload chunks use the existing background jobs. These
  features add no runtime dependencies or GPU requirement.

## Account requirements and validation

Google Drive sign-in, a real export upload, direct download to Drive, connection
reuse after restart, encrypted storage, and real token renewal were verified.
Default Drive access is limited to files used with ClipHarbor. Connecting an
existing folder by ID requests broader Drive access through Google's consent
screen. Google can require sign-in again if permission expires or is revoked.

YouTube requires separate Google upload permission and a channel, and defaults
to **Private**. Public uploads can require Google's project audit. X requires a
user access token with upload/post permissions and an explicit publish selection.
Facebook publishing supports **Pages**, requires a Page token, and defaults to
unpublished. Platform account, app-review, quota, and API access rules apply.
These three social integrations have adapter tests; real-account social
publishing has not yet been verified for this release.

The publisher's desktop app registration is included in the installer. User
access/refresh tokens, signed-in accounts, projects, and media are excluded.
The public source checkout requires publisher configuration for Google sign-in;
ordinary Windows installer users just sign in.

The installer retains the 0.5.2 graphical startup fix. The build must pass the
isolated graphical first-run, local download, editing/export, and clean shutdown
checks before an installer is produced. `SHA256SUMS.txt` verifies release assets;
`ClipHarbor-third-party-sources.zip` contains exact sources for the components
listed in the bundled notices. The Windows installer is unsigned.

[Privacy policy](https://carlfrigauss.github.io/clipharbor/privacy.html) ·
[Source and documentation](https://github.com/CarlFriGauss/clipharbor)
