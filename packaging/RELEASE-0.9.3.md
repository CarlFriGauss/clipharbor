# ClipHarbor 0.9.3

YouTube auto-translated captions could fail with HTTP 429 before any video
download began. Retrying the whole download did not help because each attempt
opened another new extraction session and immediately requested the translation.

ClipHarbor now lets that same session age for 65 seconds before fetching the
selected translated captions, following the downloader maintainer's documented
guidance. Activity shows a live countdown and cancellation remains responsive.
Download and the browser popup explain the short preparation wait in advance.
Inspection, native captions, ordinary downloads and other platforms have no
additional delay. Genuine source restrictions may still cause a failure; the
chosen caption language is never silently replaced or omitted.

No runtime dependencies, local models, browser permissions, or user credentials
are added. The earlier low-priority processing, codec thread limits, video-copy
path, burn-in rendering and switchable subtitle options remain included.

Validation includes countdown and cancellation tests, no-delay cases, source
track/download regressions, and a real English-to-Arabic translation from the
reported video. The actual translation downloaded successfully after the delay.
The frozen installer smoke checks video download, native bridge operation,
switchable subtitle streams and burned subtitle picture pixels.

Install over the previous version to retain projects and account connections.
Reopen ClipHarbor after updating. The installer includes both optional browser
extensions and the native bridge; updated extension ZIPs are also available.

Reference: [yt-dlp issue #13831](https://github.com/yt-dlp/yt-dlp/issues/13831),
[session-age fix under development upstream](https://github.com/yt-dlp/yt-dlp/pull/15709).
