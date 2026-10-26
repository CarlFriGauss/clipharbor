const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const HEADER_WIDTH = 82;
const MIN_PX_PER_SECOND = .02;
const MAX_PX_PER_SECOND = 300;

const state = {
  inspected: null, inspectedUrl: null, inspectedCookie: null, assets: [], clips: [], selectedAssetId: null,
  selectedClipIds: new Set(), primaryClipId: null, selectedLayerKeys: new Set(), previewClipId: null,
  playhead: 0, pxPerSecond: 44, videoLayerCount: 1, audioLayerCount: 1, trackState: {},
  clipboard: [], history: [], future: [], snapEnabled: true, showEmptyTracks: false,
  jobs: new Map(), lastResult: null, playingTimeline: false, playTimer: null,
  timelineAudio: new Map(), audioContext: null, mixCompressor: null, mixMaster: null,
  mixClockOrigin: 0, clockClipId: null, autoBalance: true, internalMediaPlay: false,
  ignoreClick: false, dragState: null,
  currentProjectId: null, currentProjectName: "Untitled project", projectDirty: false,
};

function zoomFromSlider(value) { return MIN_PX_PER_SECOND * Math.pow(MAX_PX_PER_SECOND / MIN_PX_PER_SECOND, Number(value) / 100); }
function sliderFromZoom(value) { return Math.log(Math.max(MIN_PX_PER_SECOND, value) / MIN_PX_PER_SECOND) / Math.log(MAX_PX_PER_SECOND / MIN_PX_PER_SECOND) * 100; }

function escapeHtml(value) { return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char])); }
function formatTime(seconds, precise = false) {
  seconds = Math.round(Math.max(0, Number(seconds) || 0) * (precise ? 100 : 1)) / (precise ? 100 : 1);
  const hours = Math.floor(seconds / 3600), minutes = Math.floor((seconds % 3600) / 60), secs = seconds % 60;
  return `${hours ? String(hours).padStart(2,"0") + ":" : ""}${String(minutes).padStart(2,"0")}:${secs.toFixed(precise ? 2 : 0).padStart(precise ? 5 : 2,"0")}`;
}
function formatBytes(bytes) {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"]; let value = bytes, unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
  return `${value.toFixed(unit > 1 ? 1 : 0)} ${units[unit]}`;
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {"Content-Type": "application/json", ...(options.headers || {})}});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
function toast(title, message = "", error = false) {
  const node = document.createElement("div"); node.className = `toast${error ? " error" : ""}`;
  node.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(message)}</span>`; $("#toastStack").append(node);
  setTimeout(() => node.remove(), 4600);
}
function setView(name) {
  $$(".view").forEach(view => view.classList.toggle("active", view.id === `${name}View`));
  $$(".nav-tab").forEach(tab => tab.classList.toggle("active", tab.dataset.view === name));
}
async function choose(kind) { return api(`/api/dialog/${kind}`, {method: "POST", body: "{}"}); }
function renderAudioTracks(info = {}) {
  const tracks=info.audioTracks||[],select=$("#audioTrackSelect");
  select.innerHTML=`<option value="">Automatic / source default</option>`+tracks.map(track=>`<option value="${escapeHtml(track.formatId)}" data-label="${escapeHtml(track.label)}">${escapeHtml(sourceLanguageLabel(track))} [${escapeHtml(track.language)}]${track.original?" · original":track.dubbed?" · dubbed":track.default?" · default":""}</option>`).join("");
  $("#audioTrackField").classList.toggle("hidden",tracks.length<2);const preferred=tracks.find(track=>track.original)||tracks.find(track=>track.default);if(preferred&&tracks.length>1)select.value=preferred.formatId;
}
function sourceLanguageLabel(track) {
  if (track.label && track.label !== track.language) return track.label;
  try { return new Intl.DisplayNames([navigator.language || "en"], {type:"language"}).of(track.language.replaceAll("_","-")) || track.language; }
  catch { return track.language; }
}
function subtitleDescription(track) {
  if(track.sourceLanguage && (track.translated || track.originalCaption)) {
    const source=sourceLanguageLabel({language:track.sourceLanguage});
    return track.translated?`translated from ${source}`:`captions for ${source} audio`;
  }
  return track.translated?"auto-translated":track.automatic?"automatic captions":"creator subtitles";
}
function updateSubtitleFormat() {
  const audioOnly=["mp3","m4a","wav"].includes($("#formatSelect").value);
  const selected=!audioOnly&&$("#subtitleTrackSelect").value!=="";
  const burn=$("#subtitleModeSelect").value==="burn";
  $("#subtitleTrackSelect").disabled=audioOnly;
  $("#subtitleModeField").classList.toggle("hidden",!selected);
  $("#burnSizeField").classList.toggle("hidden",!selected||!burn);
  $("#subtitleTrackHelp").textContent=audioOnly?"Subtitles require a video format.":!selected?"Choose a language to include subtitles.":burn?"Text is permanently visible in every player. Burning requires video encoding; source size keeps the resolution and frame rate, not the original video bitstream.":"Saved inside the video as a switchable track. Turn subtitles on in a compatible player; video is copied when the format allows.";
  if(selected&&burn&&$("#formatSelect").value==="original")$("#subtitleTrackHelp").textContent+=" Original source with burning saves an encoded MKV.";
  const track=selected?state.inspected?.subtitleTracks?.[Number($("#subtitleTrackSelect").value)]:null;
  if(track?.translated&&/^youtube$/i.test(state.inspected?.site||""))$("#subtitleTrackHelp").textContent+=" YouTube translations need about a minute to prepare; Activity shows the countdown.";
}
function renderSourceTracks(info = {}) {
  renderAudioTracks(info);
  const tracks=info.subtitleTracks||[], select=$("#subtitleTrackSelect");
  select.innerHTML=`<option value="">None</option>`+tracks.map((track,index)=>`<option value="${index}">${escapeHtml(sourceLanguageLabel(track))} [${escapeHtml(track.language)}] · ${escapeHtml(subtitleDescription(track))}</option>`).join("");
  select.value="";
  $("#subtitleTrackField").classList.toggle("hidden",!tracks.length);
  const facebook=/facebook/i.test(info.site||"");
  $("#sourceTrackNotice").classList.toggle("hidden",!facebook);
  $("#sourceTrackNotice").textContent=facebook?"Only the languages Facebook exposes for download are listed. Some translations in Facebook’s player may be unavailable here.":"";
  updateSubtitleFormat();
}
function clearSourceTracks() {
  state.inspected=null;state.inspectedUrl=null;state.inspectedCookie=null;renderSourceTracks();
}
function projectNameFromMedia(name) { return String(name || "Untitled project").replace(/\.[^.]+$/, "").trim() || "Untitled project"; }
function renderProjectHeader() {
  $("#projectTitle").textContent = state.currentProjectName || "Untitled project";
  $("#projectStatus").textContent = state.projectDirty ? (state.currentProjectId ? "Unsaved changes" : "Not saved") : (state.currentProjectId ? "Saved project" : "New project");
  $("#projectStatus").classList.toggle("dirty", state.projectDirty);
}
function markProjectDirty() { state.projectDirty = true; renderProjectHeader(); }

async function inspectSource() {
  const url = $("#urlInput").value.trim(); if (!url) return toast("A URL is needed", "Paste a public media link first.", true);
  const button = $("#inspectButton"); if(button.disabled)return; button.disabled = true; button.textContent = "Inspecting…";
  const cookieFile=$("#cookiePath").value.trim();clearSourceTracks();
  try {
    const info = await api("/api/inspect-url", {method: "POST", body: JSON.stringify({url, cookieFile})});
    if(url!==$("#urlInput").value.trim()||cookieFile!==$("#cookiePath").value.trim())return;
    state.inspected = info;state.inspectedUrl=url;state.inspectedCookie=cookieFile;
    renderSourceTracks(info);
    const thumb = info.thumbnail ? `<img src="${escapeHtml(info.thumbnail)}" alt="">` : `<div class="preview-placeholder"><span>▶</span></div>`;
    $("#sourcePreview").classList.remove("empty");
    $("#sourcePreview").innerHTML = `<div class="source-result">${thumb}<div class="source-result-info"><h3>${escapeHtml(info.title)}</h3><p>${escapeHtml(info.uploader || "Unknown creator")} · ${escapeHtml(info.site)}</p><p>${formatTime(info.duration)} · ${info.formatCount} available streams</p><div class="meta-chips"><span class="meta-chip">Best available</span>${info.maxHeight ? `<span class="meta-chip">Up to ${info.maxHeight}p</span>` : ""}${info.hasAudio ? `<span class="meta-chip">Audio</span>` : ""}</div></div></div>`;
  } catch (error) { clearSourceTracks();toast("Could not inspect this source", error.message, true); }
  finally { button.disabled = false; button.textContent = "Inspect"; }
}
async function startDownload() {
  if(state.inspectedUrl!==$("#urlInput").value.trim()||state.inspectedCookie!==$("#cookiePath").value.trim())clearSourceTracks();
  const audioOption=$("#audioTrackSelect").selectedOptions[0];
  const payload = {url: $("#urlInput").value.trim(), outputDirectory: $("#outputPath").value.trim(), outputFormat: $("#formatSelect").value, xCompatible: $("#formatSelect").value === "mp4" && $("#xCompatible").checked, audioFormatId:$("#audioTrackSelect").value||null,audioTrackLabel:$("#audioTrackSelect").value?(audioOption?.dataset.label||audioOption?.textContent||null):null,cookieFile: $("#cookiePath").value.trim()};
  const subtitleValue=$("#subtitleTrackSelect").value;
  const subtitle=!$("#subtitleTrackSelect").disabled&&subtitleValue!==""?state.inspected?.subtitleTracks?.[Number(subtitleValue)]:null;
  payload.subtitleLanguage=subtitle?.language||null;payload.subtitleSource=subtitle?.source||"manual";
  payload.subtitleMode=$("#subtitleModeSelect").value;payload.burnSize=$("#burnSizeSelect").value;
  Object.assign(payload, downloadDeliveryPayload());
  if (!payload.url || (payload.destination === "local" && !payload.outputDirectory)) return toast("Missing download details", "Enter a URL and choose an output folder for local downloads.", true);
  if(payload.destination === "drive" && !connectionStatus.drive?.connected) return toast("Connect Google Drive", "Connect your account before starting a Drive download.", true);
  downloadStarting = true; updateDownloadDestination();
  try { const job = await api("/api/downloads", {method: "POST", body: JSON.stringify(payload)}); trackJob(job); toast("Download started", payload.destination === "drive" ? "The video will upload to Google Drive after processing." : "It will continue in the background."); setView("jobs"); }
  catch (error) { toast("Download could not start", error.message, true); if(payload.destination === "drive") refreshConnections().catch(()=>{}); } finally { downloadStarting = false; updateDownloadDestination(); }
}
function trackJob(job) {
  state.jobs.set(job.id, job); updateJobs();
  const poll = async () => {
    try {
      const latest = await api(`/api/jobs/${job.id}`); latest.deliveryRequest = state.jobs.get(job.id)?.deliveryRequest; state.jobs.set(job.id, latest); updateJobs();
      if (["queued", "running"].includes(latest.status)) return setTimeout(poll, 650);
      if (latest.status === "completed") completeJob(latest); else if(latest.status === "cancelled") toast("Download cancelled"); else {toast(`${latest.kind} failed`, latest.error || "See Activity for details.", true); if(latest.result?.cloudDownloadId) refreshConnections().catch(()=>{});}
    } catch (error) { toast("Lost job status", error.message, true); }
  }; setTimeout(poll, 400);
}
async function discoverBackgroundJobs() {
  try {
    const {jobs} = await api("/api/jobs");
    for (const job of jobs) {
      const existing = state.jobs.get(job.id);
      if (existing) { state.jobs.set(job.id, {...job, deliveryRequest: existing.deliveryRequest}); continue; }
      if (["queued", "running"].includes(job.status)) trackJob(job);
      else state.jobs.set(job.id, job);
    }
    updateJobs();
  } catch { /* A temporary disconnect must not interrupt the user's timeline. */ }
}
function completeJob(job) {
  state.lastResult = job.result; const media = job.result.media, isDownload = job.kind === "download";
  const cloudDownload = Boolean(job.result.cloudDownloadId), localAvailable = !cloudDownload && Boolean(job.result.path);
  const facebookProfile=job.result.handoff?.provider==="facebook_browser";
  const finalMp4=isDownload&&media.kind==="video"&&media.name.toLowerCase().endsWith(".mp4");
  $("#completeTitle").textContent = facebookProfile ? "Video ready for Facebook" : cloudDownload ? "Saved to Google Drive" : finalMp4 ? "Final MP4 ready" : isDownload ? "Download complete" : job.result.delivery ? "Export complete" : job.kind === "upload" ? "Upload complete" : "Render complete";
  let note = finalMp4 ? `${media.name} · ${formatBytes(media.size)} · Ready to use. No editing or additional export is required.` : `${media.name} · ${formatBytes(media.size)}`;
  if(job.result.audioTrack)note+=` · Audio: ${job.result.audioTrack}.`;
  if(job.result.subtitleTrack)note+=` · Subtitles: ${sourceLanguageLabel(job.result.subtitleTrack)} [${job.result.subtitleTrack.language}] · ${job.result.subtitleRendering==="burn"?"burned into picture":"switchable track — turn on in your player"}.`;
  if (isDownload && job.result.xCompatible) note += job.result.xConversionSkipped ? " · Extra X conversion was unnecessary." : " · Verified for X.";
  if (!isDownload && job.result.xCompatible) note += " · Verified for X upload.";
  if(job.result.delivery) note += " · " + destinationNames[job.result.delivery.provider] + " · " + job.result.delivery.visibility;
  if(facebookProfile)note+=job.result.handoff.browserOpened?" · Facebook opened in your browser. Attach this file to finish posting.":" · Open Facebook below and attach this file to finish posting.";
  if(cloudDownload) note += job.result.localAvailable === false ? " · Temporary files removed from this computer." : " · " + job.result.cleanupWarning;
  $("#completeDone").textContent = cloudDownload ? "Done" : "Done — use this file";
  for(const id of ["#revealResult", "#shareResult", "#editResult"]) $(id).classList.toggle("hidden", !localAvailable);
  $("#facebookHandoff").classList.toggle("hidden",!facebookProfile);
  $("#facebookFinishHelp").textContent=(job.result.handoff?.target==="page"?"In Facebook, switch to the Page you manage first. ":"")+"Choose Photo/video, paste the copied file location into the file picker, then choose your audience and post. Your video has been prepared; it has not been uploaded or posted by ClipHarbor.";
  $("#copyFacebookCaption").classList.toggle("hidden",!facebookProfile||!job.result.handoff.caption);
  $("#facebookCopyStatus").textContent="";
  $("#openDelivery").classList.toggle("hidden",!job.result.delivery&&!facebookProfile);
  if(job.result.delivery){$("#openDelivery").href=job.result.delivery.url;$("#openDelivery").textContent="Open in "+destinationNames[job.result.delivery.provider];}
  if(facebookProfile){$("#openDelivery").href=job.result.handoff.url;$("#openDelivery").textContent="Open Facebook";}
  $("#completePath").classList.toggle("hidden", !localAvailable);
  $("#completeMessage").textContent = note;$("#completePath").textContent=job.result.path || "";$("#completeDialog").showModal();
  if(cloudDownload) refreshConnections().catch(()=>{});
}
function updateJobs() {
  const allJobs = [...state.jobs.values()].sort((a,b) => b.createdAt - a.createdAt), active = allJobs.filter(job => ["queued","running"].includes(job.status)).length;
  $("#jobCount").textContent = active; $("#jobCount").classList.toggle("hidden", !active);
  if (!allJobs.length) return $("#jobsList").innerHTML = `<div class="empty-jobs">No activity yet.</div>`;
  $("#jobsList").innerHTML = allJobs.map(job => `<article class="job-card ${escapeHtml(job.status)}"><div class="job-top"><strong>${escapeHtml(job.kind)}</strong><span class="job-status">${escapeHtml(job.status)}</span></div><div class="progress-track"><div class="progress-fill" style="width:${job.progress}%"></div></div><div class="job-message"><span>${escapeHtml(job.message || "")}</span><span>${Math.round(job.progress)}%</span></div>${jobResultMarkup(job)}${job.canCancel||job.cancelRequested&&job.status==="running"?`<button class="button ghost" data-cancel-job="${escapeHtml(job.id)}" ${job.cancelRequested?"disabled":""}>${job.cancelRequested?"Cancelling…":"Cancel download"}</button>`:""}${job.error ? `<p class="job-error">${escapeHtml(job.error)}</p>` : ""}${job.log?.length ? `<details><summary class="job-status">FFmpeg / downloader details</summary><pre class="job-log">${escapeHtml(job.log.slice(-16).join("\n"))}</pre></details>` : ""}</article>`).join("");
}
async function cancelDownload(jobId) {
  try { const job=await api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`,{method:"POST",body:"{}"});state.jobs.set(job.id,job);updateJobs(); }
  catch(error){toast("Download could not be cancelled",error.message,true);}
}
async function revealResult(result=state.lastResult){if(!result?.token)return toast("File is unavailable","The completed file is no longer registered.",true);try{await api(`/api/reveal/${encodeURIComponent(result.token)}`,{method:"POST",body:"{}"});}catch(error){toast("Folder could not be opened",error.message,true);}}
function editJobResult(jobId){const job=state.jobs.get(jobId);if(!job?.result)return;state.lastResult=job.result;addResultToEditor();}
function addResultToEditor() {
  const result = state.lastResult; if (!result) return;
  if(result.cloudDownloadId) return toast("This download is saved to Google Drive", "Choose This computer when downloading media you want to edit locally.", true);
  resetWorkspace(projectNameFromMedia(result.media?.name));
  const asset = {id: crypto.randomUUID(), path: result.path, token: result.token, media: result.media};
  state.assets.push(asset); state.selectedAssetId = asset.id; loadWaveform(asset); addClip(asset.media.kind === "video" ? "video" : "audio"); markProjectDirty();
  $("#completeDialog").close(); setView("editor"); fitTimeline(); toast("New project created", `${asset.media.name} is ready on the timeline.`);
}
async function openMedia() {
  try {
    const data = await choose("files"); for (const raw of data.assets || []) if (!state.assets.some(item => item.path === raw.path)) { const asset={...raw, id: raw.id || crypto.randomUUID()}; state.assets.push(asset); loadWaveform(asset); }
    if (data.assets?.length) { state.selectedAssetId = data.assets.at(-1).id; markProjectDirty(); renderAssets(); previewAsset(findAsset(state.selectedAssetId)); saveDraft(); }
  } catch (error) { toast("Could not open media", error.message, true); }
}

async function loadWaveform(asset) {
  if (!asset?.media?.audio || !asset.token || asset.waveform || asset.waveformLoading) return;
  asset.waveformLoading = true;
  try {
    await preparePlayback(asset);
    const sampleCount = Math.min(200000, Math.max(2000, Math.ceil(Number(asset.media.duration || 0) * 125)));
    asset.waveform = await api(`/api/waveform/${encodeURIComponent(asset.token)}?samples=${sampleCount}`);
  } catch (error) {
    asset.waveformError = error.message;
  } finally {
    asset.waveformLoading = false;
    renderTimeline();
  }
}

async function preparePlayback(asset) {
  if (asset.playbackUrl) return asset.playbackUrl;
  if (asset.media.format !== "mp3") return asset.playbackUrl = `/api/media/${encodeURIComponent(asset.token)}`;
  if (!asset.playbackReady) {
    asset.playbackLoading = true; renderAssets();
    asset.playbackReady = api(`/api/playback/${encodeURIComponent(asset.token)}`, {method:"POST",body:"{}"})
      .then(result => asset.playbackUrl = result.url)
      .catch(error => {asset.playbackReady=null;throw error;})
      .finally(() => {asset.playbackLoading=false;renderAssets();});
  }
  return asset.playbackReady;
}

function findAsset(id) { return state.assets.find(asset => asset.id === id); }
function findClip(id) { return state.clips.find(clip => clip.id === id); }
function selectedClips() { return state.clips.filter(clip => state.selectedClipIds.has(clip.id)); }
function clipDuration(clip) { return Math.max(0, (Number(clip.out) - Number(clip.in)) / Math.max(.001, Number(clip.speed))); }
function clipEnd(clip) { return Number(clip.start) + clipDuration(clip); }
function projectDuration() { return Math.max(0, ...state.clips.map(clipEnd)); }
function layerKey(kind, layer) { return `${kind}:${Number(layer)}`; }
function getTrackState(kind, layer) {
  const key = layerKey(kind, layer); if (!state.trackState[key]) state.trackState[key] = {locked:false, muted:false, hidden:false}; return state.trackState[key];
}
function isTrackLocked(clip) { return getTrackState(clip.kind, clip.layer).locked; }

function snapshotEditState() { return JSON.stringify({clips: state.clips, videoLayerCount: state.videoLayerCount, audioLayerCount: state.audioLayerCount, trackState: state.trackState}); }
function commitHistory() { state.history.push(snapshotEditState()); if (state.history.length > 60) state.history.shift(); state.future = []; markProjectDirty(); updateHistoryButtons(); }
function restoreEditState(raw) {
  const saved = JSON.parse(raw); state.clips = saved.clips; state.videoLayerCount = saved.videoLayerCount; state.audioLayerCount = saved.audioLayerCount; state.trackState = saved.trackState || {};
  clearSelection(); renderEditor();
}
function undo() { if (!state.history.length) return; state.future.push(snapshotEditState()); restoreEditState(state.history.pop()); updateHistoryButtons(); }
function redo() { if (!state.future.length) return; state.history.push(snapshotEditState()); restoreEditState(state.future.pop()); updateHistoryButtons(); }
function updateHistoryButtons() { $("#undoButton").disabled = !state.history.length; $("#redoButton").disabled = !state.future.length; }

function renderAssets() {
  $("#assetCount").textContent = `${state.assets.length} file${state.assets.length === 1 ? "" : "s"}`;
  if (!state.assets.length) return $("#assetList").innerHTML = `<button id="emptyAssetButton" class="empty-assets"><span>＋</span><strong>Add video or audio</strong><small>Sources remain untouched</small></button>`;
  $("#assetList").innerHTML = state.assets.map(asset => {
    const media = asset.media, video = media.kind === "video";
    return `<div class="asset-item ${video ? "video" : "audio"} ${asset.id === state.selectedAssetId ? "active" : ""}" data-asset-id="${asset.id}"><span class="asset-thumb">${video ? "▶" : "♫"}</span><span class="asset-copy"><strong>${escapeHtml(media.name)}</strong><small>${asset.playbackLoading ? "Preparing precise audio…" : `${formatTime(media.duration)} · ${video ? `${media.video?.width || "?"}×${media.video?.height || "?"}` : media.audio?.codec || "audio"}`}</small></span><button class="asset-remove" data-remove-asset="${asset.id}" title="Remove from this project" aria-label="Remove ${escapeHtml(media.name)} from project">×</button></div>`;
  }).join("");
}
function clearPreview() {
  state.previewRequest=(state.previewRequest||0)+1;
  $("#timelinePreviewHud").classList.add("hidden");
  for (const player of [$("#videoPlayer"),$("#audioPlayer")]) { player.pause(); player.removeAttribute("src"); player.load(); player.classList.add("hidden"); }
  $("#playerEmpty").classList.remove("hidden"); $("#previewName").textContent="No media selected"; $("#previewInfo").textContent="—"; state.previewClipId=null;
}
function removeAsset(assetId) {
  const asset=findAsset(assetId);if(!asset)return;const used=state.clips.filter(clip=>clip.assetId===assetId);
  if(used.length&&!window.confirm(`Remove ${asset.media.name} from this project? Its ${used.length} timeline section${used.length===1?"":"s"} will also be removed. The source file will not be deleted.`))return;
  commitHistory();state.assets=state.assets.filter(item=>item.id!==assetId);state.clips=state.clips.filter(clip=>clip.assetId!==assetId);if(state.selectedAssetId===assetId){state.selectedAssetId=state.assets[0]?.id||null;clearPreview();if(state.selectedAssetId)previewAsset(findAsset(state.selectedAssetId));}clearSelection();renderEditor();toast("Media removed from project","The source file was not deleted.");
}
async function previewAsset(asset, clip = null, autoplay = false, timelinePreview = false) {
  if(state.playingTimeline&&!timelinePreview)stopTimelinePlayback();
  if (!asset) return; state.selectedAssetId = asset.id; state.previewClipId = clip?.id || null;
  if(!timelinePreview){if(!clip){clearSelection();renderTimeline();}renderInspector();}renderAssets();
  const requestId = state.previewRequest = (state.previewRequest || 0)+1;
  let src;
  try {
    if(asset.media.format === "mp3" && !asset.playbackUrl) {
      selectedPlayer().pause();
      $("#previewName").textContent=asset.media.name;
      $("#previewInfo").textContent="Preparing precise audio · first use only · no re-encoding";
    }
    src = await preparePlayback(asset);
  } catch(error) {
    if(requestId===state.previewRequest){$("#previewInfo").textContent="Audio preparation failed";toast("Cannot prepare audio",error.message,true);}
    return;
  }
  if(requestId!==state.previewRequest || !findAsset(asset.id))return;
  const video = $("#videoPlayer"), audio = $("#audioPlayer"), player = asset.media.kind === "video" ? video : audio, other = player === video ? audio : video;
  // Timeline transport owns time. Native controls are only for source audition.
  player.controls = !clip;
  $("#timelinePreviewHud").classList.toggle("hidden", !clip || asset.media.kind === "video");
  if (clip && asset.media.kind !== "video") $("#previewPosition").textContent = exactTime(state.playhead);
  other.pause(); other.classList.add("hidden"); player.classList.remove("hidden"); $("#playerEmpty").classList.add("hidden");
  const sourceChanged = !player.src.endsWith(src); if (sourceChanged) player.src = src;
  player.playbackRate = Number(clip?.speed || 1); player.preservesPitch = true; player.mozPreservesPitch = true;
  player.volume = Math.min(1, Number(clip?.volume ?? 1)); player.muted = Boolean(clip?.muted || timelinePreview);
  const seek = () => { if(requestId!==state.previewRequest)return; if (clip) player.currentTime = Math.max(0, Number(clip.in) + Math.max(0, state.playhead - Number(clip.start)) * Number(clip.speed)); if (autoplay && state.playingTimeline) { state.internalMediaPlay=true; player.play().catch(() => {}).finally(()=>state.internalMediaPlay=false); } };
  if (player.readyState >= 1 && !sourceChanged) seek(); else player.addEventListener("loadedmetadata", seek, {once:true});
  $("#previewName").textContent = asset.media.name;
  $("#previewInfo").textContent = asset.media.kind === "video" ? `${asset.media.video?.codec || "video"} · ${asset.media.video?.width || "?"}×${asset.media.video?.height || "?"} · ${(asset.media.video?.fps || 0).toFixed(2)} fps` : `${asset.media.audio?.codec || "audio"} · ${asset.media.audio?.sampleRate || "?"} Hz`;
}
function selectedPlayer() { return $("#videoPlayer").classList.contains("hidden") ? $("#audioPlayer") : $("#videoPlayer"); }

function addClip(kind) {
  const asset = findAsset(state.selectedAssetId); if (!asset) return toast("Choose a source", "Select a media file from the library first.", true);
  if (kind === "video" && asset.media.kind !== "video") return toast("This is an audio source", "Place it on an audio layer.", true);
  if (kind === "audio" && !asset.media.audio) return toast("No audio stream", "This source does not contain audio.", true);
  commitHistory(); const layer = 0, previousEnds = state.clips.filter(clip => clip.kind === kind && clip.layer === layer).map(clipEnd);
  const clip = {id:crypto.randomUUID(), assetId:asset.id, kind, start:previousEnds.length ? Math.max(...previousEnds) : 0, in:0, out:Number(asset.media.duration), speed:1, volume:1, muted:false, layer};
  state.clips.push(clip); setClipSelection([clip.id], clip.id); state.playhead = clip.start; renderEditor(); previewAsset(asset, clip);
}

function clearSelection() { state.selectedClipIds.clear(); state.primaryClipId = null; state.selectedLayerKeys.clear(); }
function setClipSelection(ids, primary = null, keepLayers = false) { state.selectedClipIds = new Set(ids); state.primaryClipId = primary || ids.at(-1) || null; if (!keepLayers) state.selectedLayerKeys.clear(); }
function selectClip(id, event = {}) {
  const clip = findClip(id); if (!clip) return; const toggle = event.ctrlKey || event.metaKey;
  if (event.shiftKey && state.primaryClipId) {
    const anchor = findClip(state.primaryClipId);
    if (anchor && anchor.kind === clip.kind && anchor.layer === clip.layer) {
      const ordered = state.clips.filter(item => item.kind === clip.kind && item.layer === clip.layer).sort((a,b) => a.start-b.start), from = ordered.findIndex(item => item.id === anchor.id), to = ordered.findIndex(item => item.id === id);
      const range = ordered.slice(Math.min(from,to), Math.max(from,to)+1).map(item => item.id); setClipSelection(toggle ? [...state.selectedClipIds, ...range] : range, id); renderEditor(); previewAsset(findAsset(clip.assetId), clip); return;
    }
  }
  if (toggle) {
    if (state.selectedClipIds.has(id)) state.selectedClipIds.delete(id); else state.selectedClipIds.add(id);
    state.primaryClipId = state.selectedClipIds.has(id) ? id : [...state.selectedClipIds].at(-1) || null; state.selectedLayerKeys.clear();
  } else setClipSelection([id], id);
  renderEditor(); const primary = findClip(state.primaryClipId); if (primary) previewAsset(findAsset(primary.assetId), primary);
}
function selectLayer(kind, layer, event = {}) {
  const key = layerKey(kind, layer), ids = state.clips.filter(clip => layerKey(clip.kind, clip.layer) === key).map(clip => clip.id), toggle = event.ctrlKey || event.metaKey;
  if (!toggle) { state.selectedLayerKeys = new Set([key]); state.selectedClipIds = new Set(ids); }
  else if (state.selectedLayerKeys.has(key)) { state.selectedLayerKeys.delete(key); ids.forEach(id => state.selectedClipIds.delete(id)); }
  else { state.selectedLayerKeys.add(key); ids.forEach(id => state.selectedClipIds.add(id)); }
  state.primaryClipId = [...state.selectedClipIds].at(-1) || null; renderEditor(); const primary = findClip(state.primaryClipId); if (primary) previewAsset(findAsset(primary.assetId), primary);
}

function clipsAtPlayheadForCut() {
  const t = state.playhead, inside = clip => t > Number(clip.start) + 1e-6 && t < clipEnd(clip) - 1e-6 && !isTrackLocked(clip);
  if (state.selectedLayerKeys.size) return state.clips.filter(clip => state.selectedLayerKeys.has(layerKey(clip.kind, clip.layer)) && inside(clip));
  const chosen = selectedClips().filter(inside); if (chosen.length) return chosen;
  const primary = findClip(state.primaryClipId); return primary && inside(primary) ? [primary] : [];
}
function cutAtPlayerPosition() {
  // Never substitute a paused/stale source player's time for the user's cursor.
  if (state.playingTimeline) stopTimelinePlayback();
  const targets = clipsAtPlayheadForCut();
  if (!targets.length) return toast("Nothing to cut here", "Select a section or one or more layer headers, then place the player inside the section.", true);
  commitHistory(); const created = [];
  for (const clip of targets) { const sourcePoint = Number(clip.in) + (state.playhead - Number(clip.start)) * Number(clip.speed), right = {...clip, id:crypto.randomUUID(), in:sourcePoint, start:state.playhead}; clip.out = sourcePoint; state.clips.push(right); created.push(right.id); }
  setClipSelection(created, created[0], true); renderEditor(); const primary = findClip(state.primaryClipId); if (primary) previewAsset(findAsset(primary.assetId), primary);
  toast(`${targets.length} section${targets.length === 1 ? "" : "s"} cut`, `Created ${targets.length * 2} independently editable sections.`);
}
function copySelection() {
  const clips = selectedClips(); if (!clips.length) return toast("Nothing selected", "Select one or more sections to copy.", true);
  const origin = Math.min(...clips.map(clip => Number(clip.start))); state.clipboard = clips.map(clip => ({...clip, relativeStart:Number(clip.start)-origin}));
  toast("Sections copied", `${clips.length} section${clips.length === 1 ? "" : "s"} ready to paste.`);
}
function pasteSelection() {
  if (!state.clipboard.length) return toast("Clipboard is empty", "Copy one or more timeline sections first.", true); commitHistory();
  const pasted = state.clipboard.map(source => { const {relativeStart, ...clip} = source; if (clip.kind === "video") state.videoLayerCount = Math.max(state.videoLayerCount, Number(clip.layer)+1); else state.audioLayerCount = Math.max(state.audioLayerCount, Number(clip.layer)+1); return {...clip, id:crypto.randomUUID(), start:state.playhead + relativeStart}; });
  state.clips.push(...pasted); setClipSelection(pasted.map(clip => clip.id), pasted[0].id); renderEditor();
}
function removeSelection(ripple = false) {
  const chosen = selectedClips(); if (!chosen.length) return toast("Nothing selected", "Select one or more sections first.", true); commitHistory(); const removedIds = new Set(chosen.map(clip => clip.id));
  if (ripple) {
    const groups = new Map();
    for (const clip of chosen) { const key = layerKey(clip.kind, clip.layer); if (!groups.has(key)) groups.set(key, []); groups.get(key).push({start:Number(clip.start), end:clipEnd(clip)}); }
    for (const clip of state.clips) { if (removedIds.has(clip.id)) continue; const spans = groups.get(layerKey(clip.kind, clip.layer)) || [], shift = spans.filter(span => span.end <= Number(clip.start)+.001).reduce((sum,span) => sum + span.end-span.start, 0); clip.start = Math.max(0, Number(clip.start)-shift); }
  }
  state.clips = state.clips.filter(clip => !removedIds.has(clip.id)); clearSelection(); renderEditor();
}

function commonValue(clips, prop) { if (!clips.length) return null; const first = clips[0][prop]; return clips.every(clip => clip[prop] === first) ? first : null; }
function inspectorContext() {
  const clips=selectedClips(),layers=[...state.selectedLayerKeys],primary=findClip(state.primaryClipId);
  if(layers.length)return {kind:"layers",clips,layers,asset:primary?findAsset(primary.assetId):null};
  if(clips.length)return {kind:"sections",clips,layers:[],asset:primary?findAsset(primary.assetId):null};
  const asset=findAsset(state.selectedAssetId);return {kind:asset?"source":"empty",clips:[],layers:[],asset};
}
function renderInspector() {
  const context=inspectorContext(),clips=context.clips,primary=findClip(state.primaryClipId),asset=context.asset;
  $("#inspectorEmpty").classList.toggle("hidden",context.kind!=="empty");$("#clipInspector").classList.toggle("hidden",!clips.length);$("#sourceProperties").classList.toggle("hidden",context.kind!=="source");$("#layerProperties").classList.toggle("hidden",context.kind!=="layers");
  $("#propertiesContext").classList.toggle("hidden",context.kind==="empty");
  const layerNames=context.layers.map(key=>{const [kind,layer]=key.split(":");return (kind==="video"?"V":"A")+(Number(layer)+1);});
  $("#selectionLabel").textContent=context.kind==="layers"?layerNames.join(", "):clips.length?`${clips.length} section${clips.length===1?"":"s"}`:asset?"Source file":"No selection";$("#selectionLabel").title="";
  $("#propertiesContext").textContent=context.kind==="layers"?`Layer ${layerNames.join(", ")} · ${clips.length} section${clips.length===1?"":"s"}`:clips.length?(clips.length===1?(asset?.media.name||"Timeline section"):"Selected timeline sections"):asset?.media.name||"";
  if(context.kind==="source"){
    const media=asset.media,rows=[["Type",media.kind],["Duration",exactTime(media.duration)],["File size",formatBytes(media.size)]];
    if(media.video)rows.push(["Resolution",`${media.video.width} × ${media.video.height}`],["Frame rate",`${Number(media.video.fps||0).toFixed(2)} fps`],["Video codec",media.video.codec||"—"]);
    if(media.audio)rows.push(["Audio codec",media.audio.codec||"—"],["Sample rate",`${media.audio.sampleRate||"—"} Hz`],["Channels",media.audio.channels||"—"]);
    $("#sourceProperties").innerHTML=rows.map(([name,value])=>`<dt>${escapeHtml(name)}</dt><dd>${escapeHtml(value)}</dd>`).join("");
  }
  if(context.kind==="layers")$("#layerProperties").innerHTML=context.layers.map(key=>{const [kind,rawLayer]=key.split(":"),layer=Number(rawLayer),track=getTrackState(kind,layer);return `<div class="layer-property-row"><strong>${kind==="video"?"Video":"Audio"} layer ${layer+1}</strong><div class="layer-property-actions">${(kind==="video"?["hidden","muted","locked"]:["muted","locked"]).map(action=>`<button type="button" data-inspector-layer="${escapeHtml(key)}" data-layer-property="${action}" aria-pressed="${Boolean(track[action])}">${action==="hidden"?"Hide video":action==="muted"?"Mute":"Lock"}</button>`).join("")}</div></div>`;}).join("");
  $("#multiSelectionNotice").classList.toggle("hidden",clips.length<2);
  if (clips.length > 1) $("#multiSelectionNotice").textContent = `Editing ${clips.length} sections across ${new Set(clips.map(c => layerKey(c.kind,c.layer))).size} layer(s)`;
  if (!clips.length) return;
  $$('[data-prop]').forEach(input => {
    const prop = input.dataset.prop, value = commonValue(clips, prop);
    if (input.type === "checkbox") { input.checked = value === true; input.indeterminate = value === null; }
    else {
      const displayed = value === null ? "" : prop === "layer" ? Number(value)+1 : ["start","in","out"].includes(prop) ? Math.round(Number(value)*1000)/1000 : value;
      input.value = displayed; input.placeholder = value === null ? "Mixed" : "";
    }
  });
  const locked = clips.some(isTrackLocked); $$('[data-prop]').forEach(input => input.disabled = locked); if (primary) $("#selectionLabel").title = findAsset(primary.assetId)?.media.name || "";
}
function renderTracks() {
  const rows = [];
  for (const kind of ["video", "audio"]) {
    const count = kind === "video" ? state.videoLayerCount : state.audioLayerCount;
    for (let layer = 0; layer < count; layer++) {
      const key = layerKey(kind, layer), settings = getTrackState(kind, layer), letter = kind === "video" ? "V" : "A", clips = state.clips.filter(clip => clip.kind === kind && Number(clip.layer) === layer);
      if (!clips.length && state.clips.length && !state.showEmptyTracks) continue;
      rows.push(`<div class="track ${settings.hidden ? "hidden-track" : ""}" data-kind="${kind}" data-layer="${layer}"><div class="track-header ${state.selectedLayerKeys.has(key) ? "selected" : ""}" data-layer-key="${key}" title="Click to select this layer; Ctrl-click for multiple layers"><span class="track-name">${letter}${layer+1}</span><span class="track-buttons">${kind === "video" ? `<button class="track-mini ${settings.hidden ? "active" : ""}" data-track-action="hidden" title="Toggle visibility">◉</button>` : ""}<button class="track-mini ${settings.muted ? "active" : ""}" data-track-action="muted" title="Toggle audio">M</button><button class="track-mini ${settings.locked ? "active" : ""}" data-track-action="locked" title="Lock layer">L</button></span></div><div class="track-lane ${settings.locked ? "locked" : ""}" data-kind="${kind}" data-layer="${layer}">${clips.map(clip => renderClip(clip, settings)).join("")}</div></div>`);
    }
  } $("#tracks").innerHTML = rows.join(""); drawWaveforms();
}
function renderClip(clip, track) {
  const asset = findAsset(clip.assetId), left = Number(clip.start)*state.pxPerSecond, width = Math.max(14, clipDuration(clip)*state.pxPerSecond);
  const classes = ["timeline-clip", clip.kind, state.selectedClipIds.has(clip.id) ? "selected" : "", clip.muted || track.muted ? "muted" : "", state.dragState?.ids.has(clip.id) ? "dragging" : ""].filter(Boolean).join(" ");
  const waveform = asset?.media?.audio ? `<canvas class="clip-waveform${asset.waveformLoading ? " waveform-loading" : ""}" data-waveform-clip="${clip.id}"></canvas>` : "";
  return `<div class="${classes}" data-clip-id="${clip.id}" style="left:${left}px;width:${width}px" title="${escapeHtml(asset?.media.name)} · ${formatTime(clipDuration(clip),true)}">${waveform}<span>${escapeHtml(asset?.media.name || "Section")} · ${clip.speed}×</span></div>`;
}
let waveformFrame = null, waveformDetailTimer = null;
function scheduleWaveforms() {
  if (waveformFrame !== null) return;
  waveformFrame = requestAnimationFrame(() => { waveformFrame = null; drawWaveforms(); renderRuler(); });
}
function visibleClipRange(clip) {
  const scroller = $("#timelineScroller"), start = Number(clip.start) * state.pxPerSecond;
  const left = Math.max(0, scroller.scrollLeft - start);
  const right = Math.min(clipDuration(clip) * state.pxPerSecond, scroller.scrollLeft + scroller.clientWidth - HEADER_WIDTH - start);
  return {left, width:Math.max(0, right-left), sourceStart:Number(clip.in)+left/state.pxPerSecond*Number(clip.speed), sourceEnd:Number(clip.in)+right/state.pxPerSecond*Number(clip.speed)};
}
function waveformForRange(asset, range, step) {
  return (asset.waveformDetails || []).find(w => w.start <= range.sourceStart && w.start+w.duration >= range.sourceEnd && w.binDuration <= step * 1.05)
    || asset.waveform;
}
async function loadVisibleWaveformDetails() {
  for (const clip of state.clips) {
    const asset = findAsset(clip.assetId), range = visibleClipRange(clip);
    if (!asset?.media?.audio || !asset.token || range.width <= 0 || asset.detailLoading) continue;
    const step = Number(clip.speed) / state.pxPerSecond / 2;
    const wave = waveformForRange(asset, range, step);
    if (wave?.binDuration <= step * 1.05) continue;
    // The overview already covers wide views; do not decode hours a second time
    // while its first request is still running. Detail windows stay responsive.
    if (!wave && asset.waveformLoading && range.sourceEnd-range.sourceStart > 120) continue;
    const start = Math.max(0, Math.floor(range.sourceStart)), end = Math.min(Number(asset.media.duration), Math.ceil(range.sourceEnd)+1);
    if (end <= start) continue;
    const samples = Math.min(200000, Math.max(256, Math.ceil((end-start)/step)));
    const key = `${start}:${end}:${samples}`;
    if (asset.detailErrorKey === key) continue;
    asset.detailLoading = true;
    try {
      const detail = await api(`/api/waveform/${encodeURIComponent(asset.token)}?start=${start}&duration=${end-start}&samples=${samples}`);
      asset.waveformDetails = [detail, ...(asset.waveformDetails || [])].slice(0, 4);
      scheduleWaveforms();
    } catch (_) { asset.detailErrorKey = key; }
    finally { asset.detailLoading = false; }
  }
}
function drawWaveforms() {
  $$('[data-waveform-clip]').forEach(canvas => {
    const clip=findClip(canvas.dataset.waveformClip), asset=findAsset(clip?.assetId);
    if (!clip || !asset) return;
    const range=visibleClipRange(clip), ratio=Math.min(2,window.devicePixelRatio||1);
    // Canvas width is the viewport, never the hours-long clip stretched over it.
    canvas.style.left=`${range.left}px`; canvas.style.width=`${range.width}px`;
    canvas.width=Math.max(1,Math.ceil(range.width*ratio)); canvas.height=Math.max(20,Math.round(canvas.clientHeight*ratio));
    if (!range.width) return;
    const wave=waveformForRange(asset,range,Number(clip.speed)/state.pxPerSecond/2),values=wave?.samples;
    if(!values?.length)return;
    const step=wave.binDuration || Number(asset.media.duration)/values.length, origin=wave.start||0;
    const context=canvas.getContext("2d"),middle=canvas.height/2;
    context.fillStyle=clip.kind==="video"?"rgba(184,241,250,.75)":"rgba(225,214,255,.85)";
    const scale=asset.waveform?.peak ? wave.peak/asset.waveform.peak : 1;
    for(let x=0;x<canvas.width;x++) {
      const t0=range.sourceStart+(range.sourceEnd-range.sourceStart)*x/canvas.width;
      const t1=range.sourceStart+(range.sourceEnd-range.sourceStart)*(x+1)/canvas.width;
      const lo=Math.max(0,Math.floor((t0-origin)/step)),hi=Math.min(values.length,Math.max(lo+1,Math.ceil((t1-origin)/step)));
      let peak=0;for(let i=lo;i<hi;i++)peak=Math.max(peak,values[i]);
      const amplitude=Math.min(1,peak*scale)*middle*.92;
      context.fillRect(x,middle-amplitude,1,Math.max(.5,amplitude*2));
    }
  });
  clearTimeout(waveformDetailTimer);
  waveformDetailTimer=setTimeout(loadVisibleWaveformDetails,140);
}
function rulerInterval() {
  const target=85/state.pxPerSecond, choices=[.1,.2,.5,1,2,5,10,15,30,60,120,300,600,900,1800,3600,7200,14400];
  return choices.find(value=>value>=target)||28800;
}
function renderRuler() {
  const interval=rulerInterval(), scroller=$("#timelineScroller"), first=Math.max(0,Math.floor(scroller.scrollLeft/state.pxPerSecond/interval));
  const count=Math.ceil(scroller.clientWidth/state.pxPerSecond/interval)+2;
  $("#ruler").innerHTML=Array.from({length:count},(_,n)=>{const t=(first+n)*interval;return `<span class="ruler-mark" style="left:${t*state.pxPerSecond}px">${formatTime(t,interval<1)}</span>`;}).join("");
}
function renderTimeline() {
  const duration = Math.max(1, projectDuration()+Math.min(8,projectDuration()*.05)), width = duration*state.pxPerSecond; $("#timeline").style.width = `${width+HEADER_WIDTH}px`;
  renderRuler(); renderTracks(); updatePlayhead(); $("#snapToggle").classList.toggle("active", state.snapEnabled);$("#autoBalanceToggle").classList.toggle("active",state.autoBalance);
}
function fitTimeline() {
  const duration=Math.max(1,projectDuration()),available=Math.max(40,$("#timelineScroller").clientWidth-HEADER_WIDTH-22);
  state.pxPerSecond=Math.max(MIN_PX_PER_SECOND,Math.min(MAX_PX_PER_SECOND,available/duration));$("#timelineZoom").value=sliderFromZoom(state.pxPerSecond);renderTimeline();$("#timelineScroller").scrollLeft=0;
}
function workspaceSnapshot() {
  return {
    version:2,assets:state.assets.map(asset=>({id:asset.id,path:asset.path})),clips:state.clips,
    videoLayerCount:state.videoLayerCount,audioLayerCount:state.audioLayerCount,trackState:state.trackState,autoBalance:state.autoBalance,
    exportSettings:{format:$("#exportFormat")?.value||"mp4",canvas:$("#exportCanvas")?.value||"source",fps:$("#exportFps")?.value||"source",quality:$("#exportQuality")?.value||"master"},
  };
}
function saveDraft() {
  try { localStorage.setItem("mediaforge-workspace-v2",JSON.stringify({id:state.currentProjectId,name:state.currentProjectName,dirty:state.projectDirty,project:workspaceSnapshot()})); }
  catch (_) { /* The editor remains usable if browser storage is disabled. */ }
}
function disposeTimelineMedia() {
  stopTimelinePlayback();
  for(const engine of state.timelineAudio.values()){engine.element.pause();engine.element.removeAttribute("src");engine.element.load();}
  state.timelineAudio.clear();if(state.audioContext){state.audioContext.close().catch(()=>{});state.audioContext=null;state.mixCompressor=null;state.mixMaster=null;}clearPreview();
}
function resetWorkspace(name="Untitled project") {
  disposeTimelineMedia();state.assets=[];state.clips=[];state.selectedAssetId=null;clearSelection();state.playhead=0;state.videoLayerCount=1;state.audioLayerCount=1;state.trackState={};state.history=[];state.future=[];state.clipboard=[];state.currentProjectId=null;state.currentProjectName=name;state.projectDirty=false;renderEditor();
}
async function applyWorkspace(workspace,meta={}) {
  disposeTimelineMedia();const restored=await api("/api/assets/register",{method:"POST",body:JSON.stringify({assets:workspace.assets||[]})});const validIds=new Set(restored.assets.map(asset=>asset.id));
  state.assets=restored.assets;state.clips=(workspace.clips||[]).filter(clip=>validIds.has(clip.assetId));state.videoLayerCount=Math.max(1,Number(workspace.videoLayerCount)||1);state.audioLayerCount=Math.max(1,Number(workspace.audioLayerCount)||1);state.trackState=workspace.trackState||{};state.autoBalance=workspace.autoBalance!==false;state.selectedAssetId=state.assets[0]?.id||null;clearSelection();state.playhead=0;state.history=[];state.future=[];state.currentProjectId=meta.id||null;state.currentProjectName=meta.name||"Untitled project";state.projectDirty=Boolean(meta.dirty);
  const settings=workspace.exportSettings||{};if(settings.format)$("#exportFormat").value=settings.format;if(settings.canvas)$("#exportCanvas").value=settings.canvas;if(settings.fps)$("#exportFps").value=settings.fps;if(settings.quality)$("#exportQuality").value=settings.quality;updateExportPresetUI();state.assets.forEach(loadWaveform);renderEditor();if(state.selectedAssetId)previewAsset(findAsset(state.selectedAssetId));
}
async function restoreDraft() {
  try {
    const current=localStorage.getItem("mediaforge-workspace-v2");if(current){const draft=JSON.parse(current);return await applyWorkspace(draft.project||{},draft);}
    const legacy=localStorage.getItem("mediaforge-draft-v1");if(legacy){const workspace=JSON.parse(legacy);await applyWorkspace(workspace,{name:"Recovered project",dirty:true});localStorage.removeItem("mediaforge-draft-v1");}
  } catch (_) { localStorage.removeItem("mediaforge-workspace-v2"); }
}
function renderEditor() { renderAssets(); renderTimeline(); renderInspector(); updateHistoryButtons(); renderProjectHeader(); saveDraft(); }
function newProject() { if(state.projectDirty&&(state.assets.length||state.clips.length)&&!window.confirm("Start a new project? Save the current project first if you want to open it again later."))return;resetWorkspace();toast("New project","The timeline is ready."); }
function showSaveProjectDialog() { $("#projectNameInput").value=state.currentProjectName==="Untitled project"?"":state.currentProjectName;$("#saveProjectDialog").showModal();setTimeout(()=>$("#projectNameInput").focus(),0); }
async function saveNamedProject() {
  const name=$("#projectNameInput").value.trim();if(!name)return toast("Project name is required","Enter a name such as Project One.",true);
  try{const saved=await api("/api/projects",{method:"POST",body:JSON.stringify({id:state.currentProjectId,name,project:workspaceSnapshot()})});state.currentProjectId=saved.id;state.currentProjectName=saved.name;state.projectDirty=false;renderProjectHeader();saveDraft();$("#saveProjectDialog").close();toast("Project saved",`${saved.name} is available from Open.`);}catch(error){toast("Project could not be saved",error.message,true);}
}
async function showProjectBrowser() {
  try{const data=await api("/api/projects");$("#projectList").innerHTML=data.projects.length?data.projects.map(project=>`<div class="project-row" data-project-id="${project.id}"><span class="project-row-copy"><strong>${escapeHtml(project.name)}</strong><span>${project.clipCount} section${project.clipCount===1?"":"s"} · ${project.assetCount} media file${project.assetCount===1?"":"s"} · ${escapeHtml(new Date(project.updatedAt).toLocaleString())}</span></span><button class="button secondary" data-open-project="${project.id}">Open</button><button class="button ghost project-delete" data-delete-project="${project.id}">Delete</button></div>`).join(""):`<div class="project-list-empty">No saved projects yet.</div>`;if(!$("#projectBrowserDialog").open)$("#projectBrowserDialog").showModal();}catch(error){toast("Projects could not be loaded",error.message,true);}
}
async function openNamedProject(id) {
  if(state.projectDirty&&(state.assets.length||state.clips.length)&&!window.confirm("Open this project and replace the current unsaved workspace?"))return;
  try{const record=await api(`/api/projects/${encodeURIComponent(id)}`);await applyWorkspace(record.project||{},record);$("#projectBrowserDialog").close();setView("editor");toast("Project opened",record.name);}catch(error){toast("Project could not be opened",error.message,true);}
}
async function deleteNamedProject(id) {
  if(!window.confirm("Delete this saved project? Source media files will not be deleted."))return;
  try{await api(`/api/projects/${encodeURIComponent(id)}`,{method:"DELETE"});if(state.currentProjectId===id){state.currentProjectId=null;state.projectDirty=true;renderProjectHeader();saveDraft();}await showProjectBrowser();toast("Saved project deleted","Source media files were not deleted.");}catch(error){toast("Project could not be deleted",error.message,true);}
}
function exactTime(seconds) {
  const millis=Math.round(Math.max(0,Number(seconds)||0)*1000),hours=Math.floor(millis/3600000),minutes=Math.floor(millis/60000)%60;
  return `${hours?String(hours).padStart(2,"0")+":":""}${String(minutes).padStart(2,"0")}:${((millis%60000)/1000).toFixed(3).padStart(6,"0")}`;
}
function parsePosition(value) {
  if(!/^\d+(?::[0-5]?\d){0,2}(?:\.\d+)?$/.test(value.trim()))return NaN;
  return value.trim().split(":").reduce((time,part)=>time*60+Number(part),0);
}
function updatePlayhead() {
  $("#playhead").style.left = `${HEADER_WIDTH+state.playhead*state.pxPerSecond}px`;
  $("#timeDisplay").textContent = `/ ${formatTime(projectDuration(),true)}`;
  $("#previewPosition").textContent = exactTime(state.playhead);
  if(document.activeElement!==$("#positionInput"))$("#positionInput").value=exactTime(state.playhead);
}
function setPlayhead(seconds, preview = true) {
  // An explicit seek stops the transport; old async seek events cannot move it.
  if ((state.playingTimeline || state.preparingPlayback) && preview) stopTimelinePlayback();
  state.playhead = Math.max(0, Math.min(Number(seconds)||0, Math.max(projectDuration(),0))); updatePlayhead(); if(state.playingTimeline){if(state.audioContext)state.mixClockOrigin=state.audioContext.currentTime-state.playhead;syncTimelineAudio(true);}if (!preview) return;
  const scroller=$("#timelineScroller"),position=state.playhead*state.pxPerSecond,visibleWidth=scroller.clientWidth-HEADER_WIDTH;
  if(position<scroller.scrollLeft || position>scroller.scrollLeft+visibleWidth)scroller.scrollLeft=Math.max(0,position-visibleWidth*.3);
  const active = state.clips.filter(clip => state.playhead >= clip.start && state.playhead <= clipEnd(clip)).sort((a,b) => (a.kind === b.kind ? b.layer-a.layer : a.kind === "video" ? -1 : 1))[0]; if (active) previewAsset(findAsset(active.assetId), active);
}
function toggleTimelinePlayback() {
  if (state.playingTimeline || state.preparingPlayback) return stopTimelinePlayback(); startTimelinePlayback();
}
function clipsAreSourceContinuous(left,right) {
  return Boolean(left&&right&&left.assetId===right.assetId&&left.kind===right.kind&&Number(left.layer)===Number(right.layer)&&Math.abs(clipEnd(left)-Number(right.start))<1e-6&&Math.abs(Number(left.out)-Number(right.in))<1e-6);
}
function audioChainKey(clip) {
  const ordered=state.clips.filter(item=>item.kind===clip.kind&&Number(item.layer)===Number(clip.layer)&&item.assetId===clip.assetId).sort((a,b)=>Number(a.start)-Number(b.start));let root=null,previous=null;
  for(const item of ordered){if(!clipsAreSourceContinuous(previous,item))root=item.id;if(item.id===clip.id)return `chain:${root}`;previous=item;}return `chain:${clip.id}`;
}
function ensureAudioMixer() {
  if(state.audioContext)return state.audioContext;const AudioContextClass=window.AudioContext||window.webkitAudioContext;if(!AudioContextClass)return null;
  const context=new AudioContextClass(),compressor=context.createDynamicsCompressor(),master=context.createGain();compressor.threshold.value=-8;compressor.knee.value=6;compressor.ratio.value=8;compressor.attack.value=.003;compressor.release.value=.12;master.gain.value=.92;compressor.connect(master);master.connect(context.destination);state.audioContext=context;state.mixCompressor=compressor;state.mixMaster=master;return context;
}
function timelineAudioFor(clip) {
  const key=audioChainKey(clip);let engine=state.timelineAudio.get(key);const asset=findAsset(clip.assetId);if(!engine){const element=new Audio(asset.playbackUrl || `/api/media/${encodeURIComponent(asset.token)}`);element.preload="auto";element.preservesPitch=true;element.mozPreservesPitch=true;engine={key,element,source:null,gain:null,pendingStart:false,activeClipId:null};state.timelineAudio.set(key,engine);}const context=ensureAudioMixer();if(context&&!engine.source){engine.source=context.createMediaElementSource(engine.element);engine.gain=context.createGain();engine.gain.gain.value=0;engine.source.connect(engine.gain);engine.gain.connect(state.mixCompressor);}return engine;
}
function timelineMediaClock() {
  const candidates=state.clips.filter(clip=>{const asset=findAsset(clip.assetId),track=getTrackState(clip.kind,clip.layer);return asset?.media?.audio&&!clip.muted&&!track.muted&&state.playhead>=Number(clip.start)&&state.playhead<clipEnd(clip);}).sort((a,b)=>Number(b.kind==="video")-Number(a.kind==="video"));
  for(const clip of candidates){const engine=state.timelineAudio.get(audioChainKey(clip)),audio=engine?.element;if(audio&&!audio.paused&&audio.readyState>=2&&!audio.seeking&&Number.isFinite(audio.currentTime)){state.clockClipId=clip.id;return Number(clip.start)+(audio.currentTime-Number(clip.in))/Number(clip.speed);}}
  if(candidates.length)return state.playhead; // Hold during loading/seeking instead of running ahead of audible media.
  state.clockClipId=null;return null;
}
function syncTimelineAudio(force=false) {
  const activeKeys=new Set(),isActive=clip=>{const asset=findAsset(clip.assetId),track=getTrackState(clip.kind,clip.layer);return Boolean(asset?.media?.audio&&!clip.muted&&!track.muted&&state.playhead>=Number(clip.start)&&state.playhead<clipEnd(clip));},activeClips=state.clips.filter(isActive),videoSoundActive=activeClips.some(clip=>clip.kind==="video"),now=state.audioContext?.currentTime||0;
  for(const clip of activeClips){const engine=timelineAudioFor(clip),audio=engine.element,needsSeek=force||engine.activeClipId===null;activeKeys.add(engine.key);engine.activeClipId=clip.id;const duck=state.autoBalance&&videoSoundActive&&clip.kind==="audio" ? .38 : 1,gain=Math.max(0,Math.min(4,Number(clip.volume??1)))*duck;audio.volume=1;audio.muted=false;if(engine.gain&&Math.abs(engine.gain.gain.value-gain)>.001){engine.gain.gain.cancelScheduledValues(now);engine.gain.gain.setTargetAtTime(gain,now,.025);}
    const align=()=>{if(!state.playingTimeline||!isActive(clip))return;const speed=Number(clip.speed),target=Number(clip.in)+(state.playhead-Number(clip.start))*speed,drift=target-audio.currentTime;if(needsSeek){try{audio.currentTime=Math.max(0,target);}catch(_){}}const correction=clip.id===state.clockClipId||needsSeek ? 0 : Math.max(-.02,Math.min(.02,drift*.1));audio.playbackRate=Math.max(.25,Math.min(4,speed*(1+correction)));if(audio.paused)audio.play().catch(()=>{});};if(audio.readyState>=1)align();else if(!engine.pendingStart){engine.pendingStart=true;audio.addEventListener("loadedmetadata",()=>{engine.pendingStart=false;align();},{once:true});}
  }
  for(const [key,engine] of state.timelineAudio)if(!activeKeys.has(key)){engine.activeClipId=null;engine.element.pause();}
}
async function startTimelinePlayback() {
  if(!state.clips.length)return toast("Timeline is empty","Add a section first.",true);
  if(state.playingTimeline || state.preparingPlayback)return;
  if(state.playhead>=projectDuration())setPlayhead(0);
  const requestId=state.playRequest=(state.playRequest||0)+1;
  state.preparingPlayback=true;$("#playPause").textContent="…";
  const context=ensureAudioMixer();
  try {
    if(context)await context.resume();
    const assets=[...new Set(state.clips.map(clip=>findAsset(clip.assetId)).filter(Boolean))];
    await Promise.all(assets.map(preparePlayback));
  } catch(error) {
    if(requestId===state.playRequest){stopTimelinePlayback();toast("Playback could not start",error.message,true);}
    return;
  }
  if(requestId!==state.playRequest)return;
  state.preparingPlayback=false;state.playingTimeline=true;$("#playPause").textContent="Ⅱ";selectedPlayer().pause();
  let last=performance.now(),activeId=null;if(context)state.mixClockOrigin=context.currentTime-state.playhead;syncTimelineAudio(true);
  const tick=now=>{if(!state.playingTimeline)return;const mediaPosition=timelineMediaClock(),nextPosition=mediaPosition===null?(context?context.currentTime-state.mixClockOrigin:state.playhead+(now-last)/1000):mediaPosition;state.playhead=Math.max(state.playhead,nextPosition);if(context&&mediaPosition!==null)state.mixClockOrigin=context.currentTime-state.playhead;last=now;if(state.playhead>=projectDuration()){setPlayhead(projectDuration(),false);return stopTimelinePlayback();}updatePlayhead();syncTimelineAudio(false);
    const active=state.clips.filter(clip=>clip.kind==="video"&&state.playhead>=clip.start&&state.playhead<clipEnd(clip)&&!getTrackState(clip.kind,clip.layer).hidden).sort((a,b)=>b.layer-a.layer)[0];if(active&&active.id!==activeId){const previous=findClip(activeId),continuous=clipsAreSourceContinuous(previous,active);activeId=active.id;if(continuous){state.previewClipId=active.id;const video=$("#videoPlayer");video.playbackRate=Number(active.speed);video.muted=true;}else previewAsset(findAsset(active.assetId),active,true,true);}else if(active){const video=$("#videoPlayer"),speed=Number(active.speed),target=Number(active.in)+(state.playhead-Number(active.start))*speed,drift=target-video.currentTime,correction=Math.max(-.05,Math.min(.05,drift*.18));video.playbackRate=Math.max(.25,Math.min(4,speed*(1+correction)));video.muted=true;if(video.paused){state.internalMediaPlay=true;video.play().catch(()=>{}).finally(()=>state.internalMediaPlay=false);}}else if(activeId){activeId=null;$("#videoPlayer").pause();}state.playTimer=requestAnimationFrame(tick);};state.playTimer=requestAnimationFrame(tick);
}
function stopTimelinePlayback() { state.playRequest=(state.playRequest||0)+1;state.preparingPlayback=false;state.playingTimeline=false;state.clockClipId=null;cancelAnimationFrame(state.playTimer);$("#playPause").textContent="▶";[$("#videoPlayer"),$("#audioPlayer")].forEach(player=>player.pause());for(const engine of state.timelineAudio.values())engine.element.pause();const clip=findClip(state.previewClipId||state.primaryClipId);if(clip){const player=selectedPlayer();player.muted=Boolean(clip.muted||getTrackState(clip.kind,clip.layer).muted);} }

function snapDragDelta(primary, originalStart, rawDelta, targetLayer, selectedIds) {
  if (!state.snapEnabled) return {delta:rawDelta, edge:null}; const proposedStart = originalStart+rawDelta, proposedEnd = proposedStart+clipDuration(primary);
  const edges = [0, ...state.clips.filter(clip => !selectedIds.has(clip.id) && clip.kind === primary.kind && Number(clip.layer) === targetLayer).flatMap(clip => [Number(clip.start),clipEnd(clip)])], threshold = 10/state.pxPerSecond;
  let best = {distance:Infinity, adjustment:0, edge:null};
  for (const edge of edges) for (const boundary of [proposedStart,proposedEnd]) { const adjustment = edge-boundary, distance = Math.abs(adjustment); if (distance < best.distance && distance <= threshold) best = {distance,adjustment,edge}; }
  return {delta:rawDelta+best.adjustment, edge:best.edge};
}
function beginClipDrag(event, clipId) {
  const clip = findClip(clipId); if (!clip || isTrackLocked(clip)) return; if (!state.selectedClipIds.has(clipId)) setClipSelection([clipId],clipId); else state.primaryClipId = clipId;
  const ids = new Set(state.selectedClipIds), originals = new Map([...ids].map(id => { const item=findClip(id); return [id,{start:Number(item.start),layer:Number(item.layer),kind:item.kind}]; })), minStart = Math.min(...[...originals.values()].map(item => item.start));
  state.dragState = {ids, originals, originX:event.clientX, originY:event.clientY, primaryId:clipId, primaryLayer:Number(clip.layer), minStart, moved:false, before:snapshotEditState(), historyCommitted:false};
  const move = moveEvent => {
    const drag = state.dragState; if (!drag) return; let rawDelta = Math.max((moveEvent.clientX-drag.originX)/state.pxPerSecond,-drag.minStart);
    const lane = document.elementFromPoint(moveEvent.clientX,moveEvent.clientY)?.closest(".track-lane"); let targetLayer = drag.primaryLayer;
    if (lane?.dataset.kind === clip.kind && !getTrackState(clip.kind,Number(lane.dataset.layer)).locked) targetLayer = Number(lane.dataset.layer);
    const movedEnough = Math.abs(moveEvent.clientX-drag.originX)>3 || Math.abs(moveEvent.clientY-drag.originY)>3;
    if (!movedEnough && !drag.moved) return;
    if (movedEnough && !drag.historyCommitted) { state.history.push(drag.before); if(state.history.length>60)state.history.shift(); state.future=[]; drag.historyCommitted=true; }
    const snapped = snapDragDelta(clip,originals.get(clip.id).start,rawDelta,targetLayer,ids), deltaLayer = targetLayer-drag.primaryLayer;
    for (const id of ids) { const item=findClip(id), original=originals.get(id); item.start=Math.max(0,Math.round((original.start+snapped.delta)*1000)/1000); if(item.kind===clip.kind)item.layer=Math.max(0,Math.min((item.kind==="video"?state.videoLayerCount:state.audioLayerCount)-1,original.layer+deltaLayer)); }
    drag.moved ||= movedEnough; renderTimeline(); renderInspector();
    if (snapped.edge !== null) { $("#snapGuide").classList.remove("hidden"); $("#snapGuide").style.left=`${HEADER_WIDTH+snapped.edge*state.pxPerSecond}px`; } else $("#snapGuide").classList.add("hidden");
  };
  const up = () => { window.removeEventListener("pointermove",move); window.removeEventListener("pointerup",up); const moved=state.dragState?.moved; state.dragState=null; $("#snapGuide").classList.add("hidden"); if(moved)markProjectDirty();renderEditor(); if(moved){state.ignoreClick=true;setTimeout(()=>state.ignoreClick=false,80);} };
  window.addEventListener("pointermove",move); window.addEventListener("pointerup",up,{once:true});
}

function changeTrackState(kind,layer,prop) { commitHistory(); const track=getTrackState(kind,layer); track[prop]=!track[prop]; renderEditor(); }
function addLayer(kind) { commitHistory(); state.showEmptyTracks=true;$("#showEmptyTracks").checked=true; if(kind==="video")state.videoLayerCount++;else state.audioLayerCount++;renderEditor(); }
function updateExportPresetUI() {
  $("#exportDuration").textContent=`Timeline duration: ${exactTime(projectDuration())}. The exported file is checked against this duration.`;
  const xCompatible=$("#exportFormat").value==="x_mp4";$("#xExportNote").classList.toggle("hidden",!xCompatible);for(const id of ["#exportCanvas","#exportFps","#exportQuality"])$(id).disabled=xCompatible;
}
function serializeProject() {
  const videoAssets=state.clips.filter(clip=>clip.kind==="video").map(clip=>findAsset(clip.assetId)).filter(asset=>asset?.media?.video),primary=videoAssets.sort((a,b)=>(b.media.video.width*b.media.video.height)-(a.media.video.width*a.media.video.height))[0];
  let width=1920,height=1080;if($("#exportCanvas").value==="source"&&primary){width=Number(primary.media.video.width);height=Number(primary.media.video.height);}else if($("#exportCanvas").value!=="source"){[width,height]=$("#exportCanvas").value.split("x").map(Number);}
  const sourceFps=Math.max(1,...videoAssets.map(asset=>Number(asset.media.video.fps)||0)),fps=$("#exportFps").value==="source"?Math.min(240,sourceFps||30):Number($("#exportFps").value);
  return {version:1,settings:{width,height,fps,quality:$("#exportQuality").value,autoBalance:state.autoBalance,xCompatible:$("#exportFormat").value==="x_mp4"},assets:state.assets.map(asset=>({id:asset.id,path:asset.path,audio:Boolean(asset.media.audio),kind:asset.media.kind,duration:asset.media.duration})),clips:state.clips.map(clip=>{const track=getTrackState(clip.kind,clip.layer);return{...clip,muted:Boolean(clip.muted||track.muted),hidden:Boolean(clip.kind==="video"&&track.hidden)};})};
}
async function startExport() {
  if(exportSubmitting)return;
  exportSubmitting=true;$("#startExport").disabled=true;
  try {
  const delivery = deliveryPayload();
  if (exportSource) {
    if (delivery.destination === "local") return $("#exportDialog").close();
    try {
      const job = await api("/api/uploads", {method:"POST", body:JSON.stringify({token:exportSource.token,...delivery,requestId:exportRequestId})});
      job.deliveryRequest = delivery; trackJob(job); $("#exportDialog").close(); setView("jobs");
    } catch(error) { toast("Upload could not start", error.message, true); }
    return;
  }
  if(!state.clips.length)return toast("Timeline is empty","Add at least one section before exporting.",true);
  const preset=$("#exportFormat").value,xCompatible=preset==="x_mp4";if(xCompatible&&!state.clips.some(clip=>clip.kind==="video"&&!getTrackState(clip.kind,clip.layer).hidden))return toast("X export needs video","Choose a regular audio format for an audio-only project.",true);
  const payload={project:serializeProject(),outputDirectory:$("#exportPath").value.trim(),filename:$("#exportName").value.trim(),outputFormat:xCompatible?"mp4":preset,saveProject:$("#saveProjectFile").checked}; if(!payload.outputDirectory)return toast("Choose an output folder","The render needs a destination.",true);
  try{const job=await api("/api/renders",{method:"POST",body:JSON.stringify({...payload,...delivery,requestId:exportRequestId})});job.deliveryRequest = delivery.destination === "local" ? null : delivery;$("#exportDialog").close();trackJob(job);setView("jobs");toast("Render started","Your sources remain untouched.");}catch(error){toast("Render could not start",error.message,true);}
  } finally { exportSubmitting=false;updateDestination(); }
}
function applyInspectorChange(input) {
  const clips=selectedClips().filter(clip=>!isTrackLocked(clip));if(!clips.length)return;const prop=input.dataset.prop;let value=input.type==="checkbox"?input.checked:Number(input.value);if(input.type!=="checkbox"&&input.value==="")return;if(prop==="layer")value-=1;
  if(prop==="out"&&clips.some(clip=>value<=Number(clip.in)))return renderInspector();if(prop==="in"&&clips.some(clip=>value>=Number(clip.out)))return renderInspector();commitHistory();
  for(const clip of clips){clip[prop]=value;if(prop==="layer"){clip.layer=Math.max(0,Math.round(value));if(clip.kind==="video")state.videoLayerCount=Math.max(state.videoLayerCount,clip.layer+1);else state.audioLayerCount=Math.max(state.audioLayerCount,clip.layer+1);}}
  const primary=findClip(state.primaryClipId);if(primary)previewAsset(findAsset(primary.assetId),primary);renderEditor();
}
function handleKeyboard(event) {
  if(["INPUT","SELECT","TEXTAREA"].includes(event.target.tagName))return;const command=event.ctrlKey||event.metaKey;
  if(command&&event.key.toLowerCase()==="z"){event.preventDefault();return event.shiftKey?redo():undo();}if(command&&event.key.toLowerCase()==="y"){event.preventDefault();return redo();}
  if(command&&event.key.toLowerCase()==="c"){event.preventDefault();return copySelection();}if(command&&event.key.toLowerCase()==="v"){event.preventDefault();return pasteSelection();}
  if(command&&event.key.toLowerCase()==="a"&&$("#editorView").classList.contains("active")){event.preventDefault();setClipSelection(state.clips.map(c=>c.id),state.clips.at(-1)?.id);return renderEditor();}
  if(event.key==="Delete"||event.key==="Backspace"){event.preventDefault();return removeSelection(false);}if(event.key.toLowerCase()==="s"){event.preventDefault();return cutAtPlayerPosition();}
  if(event.code==="Space"){event.preventDefault();return toggleTimelinePlayback();}if(event.key==="Escape"){clearSelection();renderEditor();}
}

function wireEvents() {
  $$(".nav-tab").forEach(tab=>tab.addEventListener("click",()=>setView(tab.dataset.view)));$("#inspectButton").addEventListener("click",inspectSource);$("#urlInput").addEventListener("keydown",event=>{if(event.key==="Enter")inspectSource();});$("#urlInput").addEventListener("input",clearSourceTracks);$("#cookiePath").addEventListener("input",clearSourceTracks);
  $("#formatSelect").addEventListener("change",event=>{$("#xOption").classList.toggle("hidden",event.target.value!=="mp4");updateSubtitleFormat();});
  $("#subtitleTrackSelect").addEventListener("change",updateSubtitleFormat);
  $("#subtitleModeSelect").addEventListener("change",updateSubtitleFormat);
  $("#browseOutput").addEventListener("click",async()=>{const data=await choose("folder");if(data.paths[0])$("#outputPath").value=data.paths[0];});$("#browseExport").addEventListener("click",async()=>{const data=await choose("folder");if(data.paths[0])$("#exportPath").value=data.paths[0];});$("#browseCookies").addEventListener("click",async()=>{const data=await choose("cookies");if(data.paths[0]){$("#cookiePath").value=data.paths[0];clearSourceTracks();}});
  $("#downloadButton").addEventListener("click",startDownload);$("#openMedia").addEventListener("click",openMedia);$("#assetList").addEventListener("click",event=>{const remove=event.target.closest("[data-remove-asset]");if(remove){event.stopPropagation();return removeAsset(remove.dataset.removeAsset);}const item=event.target.closest("[data-asset-id]");if(item)previewAsset(findAsset(item.dataset.assetId));else if(event.target.closest("#emptyAssetButton"))openMedia();});
  $("#addVideoClip").addEventListener("click",()=>addClip("video"));$("#addAudioClip").addEventListener("click",()=>addClip("audio"));$("#addVideoLayer").addEventListener("click",()=>addLayer("video"));$("#addAudioLayer").addEventListener("click",()=>addLayer("audio"));
  $("#cutAtPlayer").addEventListener("click",cutAtPlayerPosition);$("#cutSelection").addEventListener("click",cutAtPlayerPosition);$("#copySelection").addEventListener("click",copySelection);$("#copySelectionInspector").addEventListener("click",copySelection);$("#pasteSelection").addEventListener("click",pasteSelection);
  $("#removeSelection").addEventListener("click",()=>removeSelection(false));$("#deleteClip").addEventListener("click",()=>removeSelection(false));$("#rippleDelete").addEventListener("click",()=>removeSelection(true));$("#undoButton").addEventListener("click",undo);$("#redoButton").addEventListener("click",redo);$("#snapToggle").addEventListener("click",()=>{state.snapEnabled=!state.snapEnabled;renderTimeline();});$("#autoBalanceToggle").addEventListener("click",()=>{state.autoBalance=!state.autoBalance;markProjectDirty();if(state.playingTimeline)syncTimelineAudio(false);renderTimeline();saveDraft();toast("Audio auto-balance " + (state.autoBalance?"on":"off"),state.autoBalance?"Added audio is lowered under video sound and the master peak protector prevents clipping.":"No automatic ducking; section volumes still pass through master peak protection.");});
  $("#timelineZoom").addEventListener("input",event=>{const scroller=$("#timelineScroller"),anchor=state.playhead*state.pxPerSecond-scroller.scrollLeft;state.pxPerSecond=zoomFromSlider(event.target.value);renderTimeline();scroller.scrollLeft=Math.max(0,state.playhead*state.pxPerSecond-Math.max(0,Math.min(scroller.clientWidth-HEADER_WIDTH,anchor)));scheduleWaveforms();});$("#fitTimeline").addEventListener("click",fitTimeline);$("#timeline").addEventListener("pointerdown",event=>{const node=event.target.closest("[data-clip-id]");if(node)beginClipDrag(event,node.dataset.clipId);});
  $("#timelineScroller").addEventListener("scroll",scheduleWaveforms,{passive:true});
  $("#showEmptyTracks").addEventListener("change",event=>{state.showEmptyTracks=event.target.checked;renderTimeline();});
  new ResizeObserver(scheduleWaveforms).observe($("#timelineScroller"));
  $("#positionInput").addEventListener("change",event=>{const t=parsePosition(event.target.value);if(Number.isFinite(t))setPlayhead(t);else toast("Invalid time","Use hours:minutes:seconds or seconds.",true);event.target.value=exactTime(state.playhead);});
  $("#positionInput").addEventListener("keydown",event=>{if(event.key==="Enter"){event.target.blur();}if(["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key)){event.preventDefault();setPlayhead(state.playhead+(["ArrowLeft","ArrowDown"].includes(event.key)?-1:1)*(event.shiftKey?1:.01));event.target.value=exactTime(state.playhead);}});
  wireEditorLayout();
  $("#layerProperties").addEventListener("click",event=>{const button=event.target.closest("[data-inspector-layer]");if(!button)return;const [kind,layer]=button.dataset.inspectorLayer.split(":");changeTrackState(kind,Number(layer),button.dataset.layerProperty);});
  $("#timeline").addEventListener("click",event=>{
    if(state.ignoreClick)return;const action=event.target.closest("[data-track-action]");if(action){event.stopPropagation();const track=action.closest(".track");return changeTrackState(track.dataset.kind,Number(track.dataset.layer),action.dataset.trackAction);}
    const clipNode=event.target.closest("[data-clip-id]");if(clipNode){if(!event.ctrlKey&&!event.metaKey&&!event.shiftKey){const rect=clipNode.closest(".track-lane").getBoundingClientRect();setPlayhead((event.clientX-rect.left)/state.pxPerSecond);}return selectClip(clipNode.dataset.clipId,event);}const header=event.target.closest("[data-layer-key]");if(header){const track=header.closest(".track");return selectLayer(track.dataset.kind,Number(track.dataset.layer),event);}
    const lane=event.target.closest(".track-lane");if(lane){const rect=lane.getBoundingClientRect();setPlayhead((event.clientX-rect.left)/state.pxPerSecond);if(!event.ctrlKey&&!event.metaKey){clearSelection();renderEditor();}return;}
    if(event.target.closest("#ruler")){const rect=$("#ruler").getBoundingClientRect();setPlayhead((event.clientX-rect.left)/state.pxPerSecond);}
  });
  $$('[data-prop]').forEach(input=>input.addEventListener("change",event=>applyInspectorChange(event.target)));$("#jumpStart").addEventListener("click",()=>setPlayhead(0));$("#playPause").addEventListener("click",toggleTimelinePlayback);
  $("#newProject").addEventListener("click",newProject);$("#openProject").addEventListener("click",showProjectBrowser);$("#saveProject").addEventListener("click",showSaveProjectDialog);$("#confirmSaveProject").addEventListener("click",saveNamedProject);$("#projectNameInput").addEventListener("keydown",event=>{if(event.key==="Enter")saveNamedProject();});$("#projectList").addEventListener("click",event=>{const open=event.target.closest("[data-open-project]");if(open)return openNamedProject(open.dataset.openProject);const remove=event.target.closest("[data-delete-project]");if(remove)return deleteNamedProject(remove.dataset.deleteProject);});
  $("#exportFormat").addEventListener("change",()=>{updateExportPresetUI();markProjectDirty();saveDraft();});for(const id of ["#exportCanvas","#exportFps","#exportQuality"])$(id).addEventListener("change",()=>{markProjectDirty();saveDraft();});$("#exportButton").addEventListener("click",()=>showExport());$("#startExport").addEventListener("click",startExport);$("#editResult").addEventListener("click",addResultToEditor);$("#revealResult").addEventListener("click",()=>revealResult());$("#jobsList").addEventListener("click",event=>{const cancel=event.target.closest("[data-cancel-job]");if(cancel)return cancelDownload(cancel.dataset.cancelJob);const reveal=event.target.closest("[data-job-reveal]");if(reveal)return revealResult(state.jobs.get(reveal.dataset.jobReveal)?.result);const edit=event.target.closest("[data-job-edit]");if(edit)return editJobResult(edit.dataset.jobEdit);});$$('[data-close-dialog]').forEach(button=>button.addEventListener("click",()=>button.closest("dialog").close()));
  // Source audition and timeline playback never write each other's clocks.
  [$("#videoPlayer"),$("#audioPlayer")].forEach(player=>player.addEventListener("play",()=>{if(!state.previewClipId&&state.playingTimeline)stopTimelinePlayback();}));document.addEventListener("keydown",handleKeyboard);
}
async function init() {
  wireEvents();$("#timelineZoom").value=sliderFromZoom(state.pxPerSecond);await restoreDraft();renderEditor();try{const health=await api("/api/health");$("#systemStatus").textContent=`FFmpeg ready · v${health.version}`;$("#outputPath").value=health.defaultOutput;$("#exportPath").value=health.defaultOutput;$("#quitApp").classList.toggle("hidden",!health.desktop);}catch(error){$("#systemStatus").textContent="Media tools unavailable";toast("Startup check failed",error.message,true);}
  if (location.hash === "#activity") setView("jobs");
  if (location.hash === "#download" || location.hash === "#drive") setView("download");
  if (location.hash === "#drive") {
    downloadDestination = "drive";
    localStorage.setItem("clipharbor-download-destination", "drive");
    updateDownloadDestination();
  }
  await discoverBackgroundJobs();
  setInterval(() => { if (!document.hidden) discoverBackgroundJobs(); }, 5000);
  $("#quitApp").addEventListener("click",async()=>{
    if(!confirm("Quit ClipHarbor? Save your project first if you want to continue later. Closing this app stops its local server."))return;
    try{await api('/api/desktop/quit',{method:'POST',body:'{}'});stopTimelinePlayback();document.body.innerHTML='<main style="padding:4rem"><h1>ClipHarbor is closed</h1><p>You can close this tab. Use the desktop shortcut to open the app again.</p></main>';}
    catch(error){toast('Cannot quit yet',error.message,true);}
  });
}
init();
