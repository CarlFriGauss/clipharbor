# ClipHarbor 0.9.2

Choosing subtitles now reveals a display choice in both Download and the browser
popup. **Burn into picture** makes text permanently visible, including in players
that do not display embedded subtitle tracks. **Switchable track** retains the
fast stream-copy workflow and requires enabling subtitles in a compatible player.
Subtitles still start at **None**; no text is added unless a language is selected.

Burning requires video encoding. The default keeps the source resolution and
frame rate; an explicit **Up to 1080p / 30 fps** option reduces processing time.
No source is enlarged. The separate X profile can impose its own size/FPS limits.
Original-source output with burning becomes an encoded MKV. MP4 burning uses
H.264 and preserves compatible AAC audio without re-encoding it. Arabic shaping
uses the existing FFmpeg/libass renderer. No new runtime dependencies, models,
browser permissions, or bundled accounts are added.

Managed FFmpeg operations retain bounded codec/filter threads, lower process
priority, advancing progress, and Activity's **Cancel download**. H.264 burning
avoids a lookahead/B-frame queue to reduce buffering memory. Reusing an existing
registered video can fetch only the chosen captions and leaves the
original file untouched. A failed subtitle download stops the job instead of
silently saving a video without the requested text. Source rate limits apply.

Install over the previous version to retain projects, account connections, and
folder settings. Reload the unpacked downloader extension once on Chrome/Edge's
Extensions page to load its updated popup. The installer contains both optional
extensions and the native bridge; separate ZIPs are also provided.

Validation covers real captioned output across MP4, MKV, MOV, WebM and original
output, visible pixel changes, original-audio preservation during caption-only
repair, legacy switchable tracks, invalid options, and processing cancellation.
The frozen Windows installer smoke also checks burned picture pixels through the
native extension bridge. A short 4K60 AV1 sample was visually checked for Arabic
shaping and retained resolution/frame rate. This is not a full-length encoding
benchmark. Direct social upload test status is unchanged from 0.9.1.
