# ClipHarbor 0.9.0 — Audio languages and subtitles

Inspect a source in the app or Chrome/Edge downloader extension to choose its
downloadable audio and subtitles. Subtitles start at **None**. Available creator
subtitles, automatic captions and automatic translations are labelled separately.
YouTube inspection requests its complete available translation catalogue.

Facebook's exposed audio languages use the same selector as YouTube, including
language versions supplied as a complete video. Facebook also offers Meta AI
dubbing and translated captions, but its player can expose languages that its
downloadable metadata does not. Only tracks actually exposed by the source are
listed; a video with no such tracks keeps the menus hidden. No local dubbing,
transcription or translation is performed.

The selected captions are embedded as a switchable track in MP4, MKV, MOV or
WebM. Original-quality output uses a supported source container or MKV. A player
with embedded-subtitle support is required. Video/audio are copied during the
caption remux. Normal format conversion still applies. Audio-only outputs
disable subtitles. This works for local and Google Drive downloads.

Track selections reset on a changed source. If the selected language disappears
or captions cannot be downloaded, the job fails clearly rather than silently
using another language or saving a captionless result. HTTP 429 subtitle failures
report the source's temporary rate limit. Each download uses an isolated working
directory, leaving only its final file in the chosen folder. The native host can
return larger translation catalogues while retaining its bounded incoming
messages and role separation. No new extension permission is requested.

## Weight

No runtime dependency, AI model or bundled executable is added. The feature uses
the existing yt-dlp and FFmpeg installations. Caption text is downloaded only
when selected; adding a caption track does not re-encode video or audio.

## Validation

- Real local HTTP sources exercised inspection, exact audio selection, automatic
  captions, translations, None, every video container and temporary-file cleanup.
- Packet hashes verified that the chosen audio language is preserved and that
  adding subtitles does not re-encode video or audio.
- Live YouTube inspection returned 628 caption choices on the test video. The
  live French-caption download was stopped by YouTube's HTTP 429 rate limit;
  no successful live YouTube subtitle download is claimed.
- The previously supplied Facebook reel exposed no downloadable extra audio or
  caption tracks. Facebook language selection was verified with controlled
  manifest and muxed-language fixtures; a live Facebook dubbed track has not yet
  been verified.
- Existing Drive/Facebook publishing checks remain recorded in the 0.8.1 release.
  YouTube upload testing remains deferred. This release does not post new tests.

Install over the existing app. Projects and operating-system-protected account
connections are retained. Existing unpacked extension users should reload the
downloader extension after updating; new users load its installed folder once.
