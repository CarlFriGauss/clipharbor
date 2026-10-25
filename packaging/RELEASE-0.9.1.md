# ClipHarbor 0.9.1 — Faster MP4 saves and clearer subtitle sources

Some MP4 downloads appeared stuck at 82% while converting high-resolution video.
The previous default selected the highest source video and then forced H.264
encoding, even when that source codec could be stored directly in MP4. A short
video could therefore trigger an expensive 4K/60 fps AV1-to-H.264 conversion with
unrestricted threads and a stationary processing percentage.

Normal MP4 saves now copy supported source video codecs, preserving the source's
resolution, frame rate and compressed video quality. This includes AV1, VP9,
HEVC and H.264. Some players require source-codec support. X compatibility
remains an explicit H.264 conversion when needed. Necessary conversions use two
codec threads, one managed media operation at a time and lower process priority.
Processing reports actual media time, and Activity can cancel an active source
download and terminate its managed FFmpeg child. Upload/publication is not
interrupted by that control.

Subtitle entries now identify the caption source. On a dubbed video, captions
for Arabic audio are different from an Arabic translation of English captions;
"Original" in an ASR caption identifier did not mean the video's original
spoken language. When the provider mixes translations from many dubbed audio
tracks under one language key, ClipHarbor now prefers the original audio
language and uses that same source for download.

Timestamped local diagnostics record job source identity, output format, selected
tracks, conversion decisions and periodic FFmpeg status. URL credentials and
signed query strings are omitted. YouTube video IDs are retained for diagnosis.
No account tokens or cookie contents are added to the diagnostics.

## Verification

- A three-second compressed sample from a real 4K/60 fps AV1 source saved to MP4
  in 0.16 seconds, with identical video packet hashes and about 17 MB peak FFmpeg
  working memory. This is a short-sample result, not a whole-download benchmark.
- Regression checks cover AV1 packet preservation, real progress, bounded decoder
  and encoder threads, cancellation/child cleanup, protected publication and
  original-language caption selection.
- Existing subtitle, Drive staging, editor, browser-companion and publishing
  regression tests continue to pass.

No runtime dependency, AI model, GPU requirement or extension permission is added.
Install over the existing app. Projects and protected account connections remain
in the same user data folder. Reload an existing unpacked extension once to load
the updated labels.
