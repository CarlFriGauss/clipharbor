# ClipHarbor 0.7.0 — Browser download companion

The optional Chrome/Edge extension sends the video page you are watching to
ClipHarbor without copying a URL or manually opening the editor. Choose a format
and download to your computer or the same connected Google Drive used by Download
and Export. A right-click action uses your last successful extension request's
settings. The popup, toolbar badge, and ClipHarbor Activity show download status.
The engine starts quietly on demand and continues after the popup closes.

## Install

Quit ClipHarbor and install `ClipHarbor-Setup-0.7.0-win-x64.exe` over the old
version. Existing projects, downloads and account connections are preserved.
Windows 10/11 x64; first-run media-tool setup is unchanged.

The installer includes and registers a small stdio bridge for Chrome/Edge. It
also includes the `browser-extension` folder. Open `chrome://extensions` or
`edge://extensions`, enable Developer mode, choose **Load unpacked**, and select
`%LOCALAPPDATA%\Programs\ClipHarbor\browser-extension`. Alternatively extract
`ClipHarbor-Extension-0.7.0.zip` to a permanent folder and load it. Pin ClipHarbor.
This release is distributed through GitHub, not either browser's extension store.
No extension is force-installed and no browser policy is changed.

## Lightweight and private

No new runtime dependencies, hosted processing service, browser scanner, cookie
access, or broad website permissions. The extension reads the invoked tab's URL
and visible media/permalinks using temporary activeTab access. Media processing
uses the existing app engine. The bridge accepts only this extension's stable ID,
uses framed messages with bounded sizes, and keeps session secrets and Google
tokens out of extension responses. Desktop localhost/origin/session protections
remain in force. Folder/format choices and recent download status stay local.

Google sign-in is shared with the existing app. If a login is needed, the popup
opens ClipHarbor's existing sign-in flow. The app's Drive folder is reused;
temporary media is removed only after upload verification. Failed Drive uploads
can be retried from Activity. No automatic cookie transfer is implemented.

Some feeds do not expose individual video links; select or paste a permalink.
Site authentication and protected-stream limitations still apply. Job state
belongs to the running desktop engine; a crash/restart can lose that state.
The extension never automatically retries a failed submission or lost job.

## Source builds and validation

Source users can register their existing Python environment with
`python browser-extension/register_host.py` and load the source extension folder.
Windows registration and packaged execution are tested. macOS/Linux source
registration paths are included but require live platform validation. Google
publisher registration requirements for source builds remain unchanged.

Regression checks cover native framing/size limits, caller and URL validation,
session isolation, extension identity/permissions, safe download arguments,
concurrent job tracking, no silent resubmission, and shared Activity. The packaged
smoke check exercises native bridge download/progress, background engine startup,
and clean shutdown with developer tools removed from PATH, in addition to the
existing media, project, and graphical first-run checks.

The four-area editor, Facebook browser handoff, and other export integrations
remain included. YouTube live upload testing remains deferred until the test
account's temporary restriction ends. No new social post is made in this release.
