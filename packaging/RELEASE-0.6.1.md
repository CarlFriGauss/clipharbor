# ClipHarbor 0.6.1 — Flexible editor layout and Facebook sharing

Download **ClipHarbor-Setup-0.6.1-win-x64.exe**, quit ClipHarbor, and install
over the existing version. Projects, media, and saved Google connections remain
in your per-user data directory. Windows 10/11 x64; no separate runtime setup.

## Editor layout

Media occupies the left sidebar, preview the center, Properties the right, and
the timeline the full bottom width. Drag both vertical dividers and the horizontal
timeline divider to resize. The folder icon toggles Media (yellow when open).
Panel sizes and the toggle are remembered in the browser. The video fits the
entire preview area without cropping, for portrait and landscape sources.
Fullscreen is a separate action, with in-window expansion if the browser denies
native fullscreen. Escape restores the editor.

Properties follows the current selection: source-file details, editable timeline
sections, or layer controls. Selecting an empty layer also shows that layer's
properties; multiple selected sections retain mixed/common-value editing.

## Facebook sharing

Choose **Export → Facebook → Personal profile** to prepare an MP4 and open
Facebook. The completion dialog provides **Copy video location**, **Copy post
text**, and **Open Facebook**. Choose **Photo/video** in Facebook, attach the
file, choose the audience, and finish posting there. Activity keeps a
**Continue in Facebook** action. Existing MP4 downloads are shared without
rendering again; edited timelines render first.

Facebook does not offer a direct personal-profile video publishing API. This is
a browser handoff: ClipHarbor reports **Video ready for Facebook**, never a
successful upload or post. Facebook handles sign-in in the browser; ClipHarbor
does not request or store a Facebook password or access token for this option.
If the browser does not open automatically, the local video and fallback link
remain available. No SDK, browser automation dependency, or GPU requirement is
added to the app.

**Page I manage · finish in Facebook** offers the same browser flow for Page
owners without developer configuration. Switch to your Page in Facebook before
attaching the video. The advanced **Page · direct API upload** option retains
direct API uploads with a Page token.
Google Drive, YouTube, and X integrations remain included. Real Drive export,
direct download, shared sign-in, restart, and token renewal were verified in
0.6.0. YouTube sign-in and the upload permission were verified, but its live
upload test is deferred while the test account has an upload restriction.
The Facebook browser flow was tested end to end with a generated three-second
video, a successful **Only me** post, and playback on Facebook. Direct Facebook
Page API publishing and X still require real-account validation.

The installer includes the Google desktop registration. It is excluded from Git;
advanced source builds need publisher configuration as documented in the README.
The registration contains app identity, never user
tokens, projects, or media. It retains the graphical first-run startup fix and
must pass the isolated packaged smoke checks before publication.
