# ClipHarbor browser companion

Chrome and Edge, Manifest V3. Requires ClipHarbor 0.7.0 or newer on the same
computer. The Windows installer registers the local bridge. No cloud processing,
browser cookies, browsing history permission, or access to all websites is used.

1. Install ClipHarbor and finish its first-run tool setup once.
2. Visit `chrome://extensions` (Chrome) or `edge://extensions` (Edge).
3. Enable **Developer mode**, click **Load unpacked**, and select this folder.
4. Pin ClipHarbor, open a video page, and click the extension. Choose the link,
   format and **This computer** or **Google Drive**, then download.

The Windows installer includes this folder at
`%LOCALAPPDATA%\Programs\ClipHarbor\browser-extension`. Alternatively extract
`ClipHarbor-Extension-0.7.0.zip` from the GitHub release and load its extracted
folder. Keep the folder in place. This version is not in either browser's store.
No browser policies are changed and extensions are never silently force-installed.

Right-click **Download with ClipHarbor** uses your last successful extension
request's format and destination. Downloads continue after closing the popup.
The badge and popup show progress. **Open app** opens Activity, where background
downloads can be opened, edited, or exported using the existing app controls.
Jobs are held by the running desktop engine; a crash or app restart can lose
job status. A disconnected job is never silently submitted a second time.

For Drive, **Connect in ClipHarbor** opens the app's Google sign-in. Download,
Export, and the extension share that connection and its dedicated folder.
Reopen the popup after connecting. Google tokens stay in the operating-system
credential store, not the extension. Browser storage keeps recent job IDs,
progress and output locations; desktop storage remembers folder/format choices.

The extension reads the invoked page's URL and visible media/permalink elements
using temporary `activeTab` access. There is no page scanner running on every
site, cookie/password access, remote executable code, or analytics. Only the
extension ID `nopjlekidanihaoahnpcnkacdpgljejl` is allowed to contact the bridge.
The manifest's public key makes that ID stable when loading this GitHub build.
It is public app identity, not a private credential or an authenticity guarantee.
Store publication would require review and aligning the store-assigned ID/key
with the bridge allowlist; do not remove the allowlist to accommodate it.

Some social feeds do not expose the selected video's permalink. Choose or paste
the individual link in the popup in that case. The downloader's site support and
authentication/DRM limits still apply. Cookies are never copied automatically.

## Source registration (Windows, macOS, Linux)

Install the normal source dependencies first, including Waitress and media tools.
Using that Python environment, from the complete repository checkout run:

```sh
python browser-extension/register_host.py
```

Then load this folder as above. Keep the source checkout, environment and folder
in place. The script registers Chrome, Edge, and (on Unix) Chromium per user.
It starts the source desktop engine on demand, not the Flask development server.
It needs no administrator rights. Windows source and packaged app registrations
use the same name; the most recent registration wins. Re-run the installer to
switch back to the packaged app, or re-run this script for the source checkout.

```sh
python browser-extension/register_host.py --unregister
```

Unregister removes only matching source registrations; user media and Google
connections are preserved. macOS/Linux registration paths are provided but need
live platform validation; Windows is the tested installer platform.

For bridge-unavailable errors, confirm that the app/extension versions match,
the loaded extension ID matches the one above, and the bridge registration points
to the current installation. If media tools need setup, open ClipHarbor once.
For a failed job, open Activity and read its error before starting another download.
