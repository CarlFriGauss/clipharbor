# ClipHarbor 0.8.1 — Drive destinations and Facebook posting

Choose a Google Drive destination through Google's folder picker in Download,
Export or the downloader extension. One remembered account and folder are shared
across those features. Access uses the limited drive.file permission; no user
Cloud configuration or API key is required in the Windows installer.

The optional separate Facebook companion attaches the exported video, enters
the caption, verifies the selected audience and posts through your signed-in
browser. Only me is the initial audience. Load the installed `facebook-extension`
folder once, then connect it from your own Facebook profile. The ordinary
downloader does not gain Facebook host or debugger permission.

The companion requires Chrome's powerful debugger permission, which is not
technically limited to one website. Companion code attaches only to the dedicated
Facebook tab it creates. It does not copy passwords or cookies. Existing drafts,
security checks or unrecognized controls stop posting; an uncertain publication
is never automatically retried. This remains experimental website automation,
and Facebook layout or language changes can require adapter updates. Manual
Facebook preparation and the advanced official Page API remain available.

## Repeated submission protection

Rapid clicks while submitting one Export dialog create one job. Retrying that
same request after a delayed response returns its existing job. A failed export
has one linked retry: repeated clicks on the original Retry action return that
retry even after it completes, and the old action disappears. A retry that fails
before publication can itself be retried. An uncertain Facebook publication
cannot use ordinary Retry. A new explicit Export dialog is a separate action.

The live test exposed the original failed card remaining available after a
successful retry. This version fixes that issue in both the interface and the
desktop job manager, with concurrent-request and API regression checks.

## Verified behavior

Live Windows/Chrome checks completed Google folder selection, exported a neutral
three-second video into that folder, and downloaded the same test media directly
to the selected folder. Drive confirmed size and destination. The direct
download's temporary local directory was removed afterward.

The Facebook companion connected, preserved an existing draft by stopping, and
then completed automatic attachment, caption entry, Only me selection and
publication after the user handled the draft. Facebook confirmed the private
post, and Activity reported completion. No YouTube upload was attempted; its
live test remains deferred until the test account's restriction ends.

121 Python tests passed, with one existing skip. Browser regressions also passed.
Automated checks cover concurrent and repeated export/retry requests, uncertain
posts, scope and folder validation, protected credentials, both extensions and
the existing timeline. The packaged Windows smoke test exercises first-run tool
setup, download/export, the native bridge, background startup and clean shutdown.
The installer contains the app and both optional extension folders. Account
connections remain in protected per-user storage when updating.
