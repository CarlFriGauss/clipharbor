# ClipHarbor 0.8.0 — Drive folder chooser and optional Facebook posting

The Windows installer includes the app, downloader extension, and a separate
optional Facebook posting companion. Install over the previous version; media,
projects and protected Google connections stay in user data.

## Google Drive destinations

Download, Export, and the downloader extension offer **Choose Drive folder**.
Google’s desktop picker lets you browse and choose a writable folder with limited
drive.file access. The selected folder and account are shared and remembered.
No API key or Cloud setup is asked of installer users. The publisher must enable
Google Picker API once; it is enabled for the ClipHarbor publisher project.

Invalid, cancelled and read-only selections preserve the previous connection.
Queued jobs keep their original destination when the default changes. Advanced
manual folder IDs remain available separately and can require broader access.

## Optional Facebook browser posting

Load the separate `facebook-extension` folder in Chrome/Edge (also available as
`ClipHarbor-Facebook-Companion-0.8.0.zip`), open your own Facebook profile and
connect it once. Export offers **My profile · post through browser companion**:
enter the caption, choose the audience, and post. Only me is the initial audience.

This is experimental browser automation, not Meta’s personal-profile upload API.
It uses your signed-in Facebook website. Chrome’s powerful debugger permission
is required to attach the local file without copying its contents into extension
memory. Chrome cannot request that permission optionally; this is why posting
uses a separate optional extension. The ordinary downloader gains no Facebook
host or debugger permission. Although companion code attaches only to Facebook
tabs it creates, the debugger permission itself is not technically restricted
to that website. Review this access before installing the optional component.

An existing draft/attachment, login or security check, unrecognized controls,
unavailable audience, or interrupted browser stops the task. Local media is kept.
No password or cookie is copied to the app. The chosen audience is verified and
your default audience is left unchanged. Each task is claimed once. Missing
confirmation after the Post attempt is uncertain and is never automatically
resubmitted; check your profile before trying again. Manual Facebook preparation
and the official advanced Page API remain available separately.

English desktop Facebook is the primary live-validation target. Other interface
variants and browser/platform combinations can need adapter updates. Automated
checks are not a substitute for a live post test. YouTube live-upload testing
remains deferred until the test account’s temporary restriction ends.

## Validation

114 Python checks passed, with one existing skip. Node regressions cover both
extensions and the existing timeline. Picker tests cover scope, cancellation,
writable destinations, retained credentials and queued destination snapshots.
Posting tests cover caller separation, single claims, audience acknowledgement,
no automatic resubmission, draft/attachment preservation and login/origin stops.
The packaged smoke test covers graphical first-run setup, isolated PATH, saved
projects, actual download/export, native progress, cold startup and clean quit.
