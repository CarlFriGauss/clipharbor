# ClipHarbor 0.9.4

Download now defaults to **Original source** with selectable subtitles. Adding
captions or choosing a dubbed audio track copies the selected video and audio
without re-encoding. The audio-language menu follows yt-dlp's quality ranking,
instead of treating a larger bitrate from a different codec as better quality.

Ordinary MP4, MKV, MOV and WebM downloads preserve the media streams. If the
requested container cannot hold their codecs, ClipHarbor uses MKV with an
explicit notice. Opus and multichannel AAC are retained, without silent AAC
conversion or stereo downmixing. Captions are muxed with the media in one pass,
and original-source downloads needing no changes avoid an extra remux.

**Burn into picture** is optional and clearly marked as video re-encoding.
Keeping the source resolution and frame rate does not preserve the original
compressed video. Burn-in, X compatibility and audio-format conversion remain
explicit conversions. No source size/FPS reduction is applied to ordinary
quality-preserving downloads.

Activity and the extension show the actual current stage percentage. An encode
at 60% no longer appears to be 90% complete because of a weighted overall bar.
Cancellation, lower-priority processing and bounded codec threads remain.

The YouTube translated-caption preparation wait and countdown remain included.
No runtime dependencies, models, GPU requirement, browser permissions or account
connections are added. Install over the previous version to keep user data.

Validation includes packet-hash comparisons for copied video, Opus and
multichannel AAC, codec/container fallback, cancellation, real caption muxing,
fresh default settings, HTML subtitle defaults and stage-progress regressions.
The frozen Windows build verifies media packet identity through the native
browser bridge. Live validation uses the reported 4K YouTube source with its
best original-language audio and Arabic translated subtitles.
