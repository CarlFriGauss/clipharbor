import {HOST, ACTIVE, cleanUrl, contextUrl} from "./shared.js";

async function native(action, fields = {}) {
  let response;
  try { response = await chrome.runtime.sendNativeMessage(HOST, {protocol: 1, action, ...fields}); }
  catch { throw new Error("ClipHarbor's browser bridge is unavailable. Install ClipHarbor 0.9.3 or newer, then try again. Source users: register the bridge first."); }
  if (!response?.ok) throw new Error(response?.error || "ClipHarbor could not complete the request.");
  return response;
}

async function updateBadge() {
  const {downloads = [], lastError} = await chrome.storage.local.get(["downloads", "lastError"]);
  const count = downloads.filter(item => ACTIVE.has(item.status)).length;
  const failed = Boolean(lastError) || downloads.some(item => item.status === "failed");
  await chrome.action.setBadgeText({text: count ? String(count) : failed ? "!" : downloads.length ? "✓" : ""});
  await chrome.action.setBadgeBackgroundColor({color: failed && !count ? "#b83e45" : "#607715"});
  await chrome.action.setTitle({title: count ? `ClipHarbor · ${count} download${count === 1 ? "" : "s"} running` : failed ? "ClipHarbor · open for download details" : "Download with ClipHarbor"});
  if (count) await chrome.alarms.create("downloads", {periodInMinutes: 0.5});
  else await chrome.alarms.clear("downloads");
}

// Serialize storage updates so simultaneous right-clicks/popup polls cannot
// drop an accepted job. A download is submitted once and never silently retried.
let pending = Promise.resolve();
function serial(task) {
  const work = pending.then(task, task);
  pending = work.catch(() => {});
  return work;
}

async function startDownload(fields) {
  if (!cleanUrl(fields.url)) throw new Error("Open a video page or enter a complete http:// or https:// link.");
  const {job} = await native("download", {url: fields.url, destination: fields.destination, outputFormat: fields.outputFormat, xCompatible: fields.xCompatible === true,
    audioFormatId:fields.audioFormatId||null,audioTrackLabel:fields.audioTrackLabel||null,
    subtitleLanguage:fields.subtitleLanguage||null,subtitleSource:fields.subtitleSource||"manual",
    subtitleMode:fields.subtitleMode||"embed",burnSize:fields.burnSize||"source"});
  const {downloads = []} = await chrome.storage.local.get("downloads");
  // Never evict an active download from background tracking.
  const retained = downloads.filter(item => ACTIVE.has(item.status));
  retained.push(...downloads.filter(item => !ACTIVE.has(item.status)).slice(0, 9));
  await chrome.storage.local.set({downloads: [{...job, destination: fields.destination, createdAt: Date.now()}, ...retained], lastError: null});
  await updateBadge();
  return {job};
}

async function refreshDownloads() {
  const {downloads = []} = await chrome.storage.local.get("downloads");
  for (let i = 0; i < downloads.length; i++) {
    const item = downloads[i];
    if (!ACTIVE.has(item.status)) continue;
    try { downloads[i] = {...item, ...(await native("job", {jobId: item.id})).job}; }
    catch (error) { downloads[i] = {...item, status: "failed", error: error.message + " Open Activity in ClipHarbor before retrying."}; }
  }
  await chrome.storage.local.set({downloads});
  await updateBadge();
  return {downloads};
}

chrome.runtime.onInstalled.addListener(details => {
  chrome.contextMenus.removeAll(() => chrome.contextMenus.create({id: "download", title: "Download with ClipHarbor", contexts: ["page", "link", "video", "audio"], documentUrlPatterns: ["http://*/*", "https://*/*"]}));
  if (details.reason === "install") chrome.tabs.create({url: chrome.runtime.getURL("setup.html")});
});
chrome.contextMenus.onClicked.addListener(info => {
  if (info.menuItemId !== "download") return;
  serial(async () => {
    try {
      const {settings} = await native("status");
      await startDownload({...settings, url: contextUrl(info)});
    } catch (error) {
      await chrome.storage.local.set({lastError: error.message});
      await updateBadge();
    }
  });
});
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === "downloads") serial(refreshDownloads); });
chrome.runtime.onStartup.addListener(() => serial(refreshDownloads));
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id || sender.tab) return false;
  serial(async () => {
    switch (message?.action) {
      case "status": return native("status");
      case "inspect": return native("inspect", {url:message.url});
      case "download": return startDownload(message);
      case "jobs": return refreshDownloads();
      case "chooseFolder": return native("chooseFolder");
      case "chooseDriveFolder": return native("chooseDriveFolder");
      case "connectionJob": return native("job", {jobId: message.jobId});
      case "open": return native("open", {view: message.view});
      case "reveal": return native("reveal", {jobId: message.jobId});
      default: throw new Error("Unknown extension action.");
    }
  }).then(result => reply({ok: true, ...result}), error => reply({ok: false, error: error.message}));
  return true;
});
