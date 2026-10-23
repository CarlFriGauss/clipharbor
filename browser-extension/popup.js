import {ACTIVE, cleanUrl, discoverMedia} from "./shared.js";
const $ = id => document.getElementById(id);
let connected = false, busy = false, drive = {}, polling = false;

async function request(action, fields = {}) {
  const response = await chrome.runtime.sendMessage({action, ...fields});
  if (!response?.ok) throw new Error(response?.error || "ClipHarbor is unavailable. See Setup & privacy below.");
  return response;
}
function message(text, error = false) { $("message").textContent = text; $("message").classList.toggle("error", error); }
function update() {
  const remote = $("destination").value === "drive";
  $("folderRow").hidden = remote; $("driveRow").hidden = !remote;
  $("compatibility").hidden = $("format").value !== "mp4";
  $("driveStatus").textContent = drive.connected ? (drive.folderName || "ClipHarbor Exports") : drive.needsReconnect ? "Sign in to Drive again" : "Google Drive is not connected";
  $("connectDrive").hidden = Boolean(drive.connected);
  $("download").disabled = !connected || busy || !cleanUrl($("url").value) || (remote && !drive.connected);
  $("download").textContent = busy ? "Starting…" : remote ? "Download to Google Drive" : "Download to this computer";
  $("chooseFolder").disabled = !connected || busy;
}
async function openApp(view = "activity") {
  try { await request("open", {view}); }
  catch (error) { message(error.message, true); }
}
function renderJobs(downloads) {
  $("activity").hidden = !downloads.length;
  const elements = downloads.slice(0, 10).map(job => {
    const article = document.createElement("article"), title = document.createElement("strong"), status = document.createElement("p");
    title.textContent = job.name || (job.destination === "drive" ? "Google Drive download" : "Video download");
    status.textContent = job.status === "failed" ? job.error || "Download failed" : `${job.message || job.status}${ACTIVE.has(job.status) ? ` · ${Math.round(job.progress || 0)}%` : ""}`;
    if (job.status === "failed") status.className = "job-error";
    article.append(title, status);
    if (ACTIVE.has(job.status)) { const progress = document.createElement("progress"); progress.max = 100; progress.value = job.progress || 0; progress.setAttribute("aria-label", "Download progress"); article.append(progress); }
    if (job.status === "completed" && job.path) {
      const button = document.createElement("button"); button.textContent = "Open folder"; button.className = "quiet";
      button.addEventListener("click", () => request("reveal", {jobId: job.id}).catch(error => message(error.message, true))); article.append(button);
    }
    if (job.driveUrl && /^https:\/\/drive\.google\.com\//.test(job.driveUrl)) {
      const link = document.createElement("a"); link.href = job.driveUrl; link.textContent = "View in Google Drive ↗"; link.target = "_blank"; link.rel = "noreferrer"; article.append(link);
    }
    return article;
  });
  $("jobs").replaceChildren(...elements);
}
async function refresh() {
  if (polling || !connected || busy) return;
  polling = true;
  try { renderJobs((await request("jobs")).downloads); }
  catch (error) { message(error.message, true); }
  finally { polling = false; }
}
async function currentPage() {
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    const pageUrl = cleanUrl(tab?.url);
    if (!pageUrl) return;
    $("url").value = pageUrl;
    const options = [{url: pageUrl, label: "Current page"}];
    try {
      const [{result = []}] = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: discoverMedia});
      for (const item of result) if (cleanUrl(item.url) && !options.some(option => option.url === item.url)) options.push(item);
      if (result[0] && cleanUrl(result[0].url)) $("url").value = result[0].url;
    } catch { /* Some browser-managed pages disallow injection; the editable URL still works. */ }
    $("candidate").replaceChildren(...options.map(item => new Option(item.label, item.url, false, item.url === $("url").value)));
    $("mediaChoices").hidden = options.length < 2;
  } finally { update(); }
}
$("candidate").addEventListener("change", () => { $("url").value = $("candidate").value; update(); });
for (const id of ["url", "format", "destination"]) $(id).addEventListener("input", update);
$("openApp").addEventListener("click", () => openApp());
$("connectDrive").addEventListener("click", () => openApp("drive"));
$("chooseFolder").addEventListener("click", async () => {
  busy = true; update(); message("Choose a folder in the ClipHarbor dialog.");
  try { const {settings} = await request("chooseFolder"); $("folder").textContent = settings.outputDirectory; message(""); }
  catch (error) { message(error.message, true); }
  finally { busy = false; update(); }
});
$("downloadForm").addEventListener("submit", async event => {
  event.preventDefault(); if ($("download").disabled) return;
  busy = true; update(); message("");
  try {
    await request("download", {url: $("url").value.trim(), outputFormat: $("format").value, destination: $("destination").value, xCompatible: $("xCompatible").checked});
    message("Download started. You can close this popup.");
  } catch (error) { message(error.message, true); }
  finally { busy = false; update(); await refresh(); }
});
async function init() {
  currentPage();
  const {lastError} = await chrome.storage.local.get("lastError");
  if (lastError) { message(lastError, true); await chrome.storage.local.remove("lastError"); }
  try {
    const status = await request("status"); connected = true; drive = status.drive;
    $("connection").textContent = `Connected · ClipHarbor ${status.version}`;
    $("destination").value = status.settings.destination; $("format").value = status.settings.outputFormat;
    $("xCompatible").checked = status.settings.xCompatible; $("folder").textContent = status.settings.outputDirectory;
    update(); await refresh();
  } catch (error) { $("connection").textContent = "Desktop app connection needed"; message(error.message, true); update(); }
}
init(); setInterval(refresh, 3000);
