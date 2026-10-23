/* Downloader destinations share the existing account connections and upload adapters. */
let downloadDestination = localStorage.getItem("clipharbor-download-destination") === "drive" ? "drive" : "local";
let downloadConnecting = false;
let downloadStarting = false;

function updateDownloadDestination() {
  const remote = downloadDestination === "drive";
  const connected = Boolean(connectionStatus.drive?.connected);
  const signingIn = downloadConnecting || googleSignIns.has("drive");
  $$("[data-download-destination]").forEach(button => {
    const selected = button.dataset.downloadDestination === downloadDestination;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  $("#outputPath").disabled = remote;
  $("#browseOutput").disabled = remote;
  $("#downloadOutputLabel").textContent = remote ? "Local output folder · used for This computer" : "Output folder";
  $("#downloadDrivePanel").classList.toggle("hidden", !remote);
  $("#downloadGoogleSetup").classList.toggle("hidden", connected);
  $("#downloadDisconnectDrive").classList.toggle("hidden", !connected);
  $("#downloadDisconnectDrive").disabled = signingIn;
  $("#downloadConnectDrive").disabled = signingIn || !connectionStatus.drive?.googleConfigured;
  $("#downloadDriveFolderId").disabled = signingIn;
  if(!downloadConnecting) $("#downloadDriveStatus").textContent = signingIn ? "Finish signing in in your browser" : connected ? "Google Drive connected" : connectionStatus.drive?.needsReconnect ? "Sign in to Google Drive again" : "Connect Google Drive";
  $("#downloadGoogleHelp").textContent = !connectionStatus.drive?.googleConfigured ? "Google sign-in is not available in this ClipHarbor build yet. The publisher needs to enable it once; you do not need configuration files." : "Sign in with Google in your browser once. The same protected connection works in Download and Export and is remembered on this computer. ClipHarbor never receives your Google password.";
  $("#downloadDriveFolderNote").textContent = "Folder: " + (connectionStatus.drive?.folderName || "ClipHarbor Exports") + (connectionStatus.drive?.folderId ? "" : " · created on the first upload.");
  $("#downloadStorageNote").textContent = remote
    ? "Temporary space is used while downloading and processing. Files are removed after Google Drive verifies the upload. Failed uploads stay available to retry or discard in Activity."
    : "Save the finished file to your output folder.";
  $("#downloadButton").disabled = downloadStarting || (remote && (!connected || signingIn));
  $("#downloadButton").innerHTML = remote ? "<span>Download to Google Drive</span><span>↑</span>" : "<span>Download best quality</span><span>↓</span>";
}

function downloadDeliveryPayload() {
  return {destination: downloadDestination, deliveryOptions: downloadDestination === "drive" ? {folderId: $("#downloadDriveFolderId").value.trim()} : {}};
}

function cloudDownloadMarkup(job) {
  const result = job.result;
  if(!result?.cloudDownloadId) return "";
  const id = escapeHtml(result.cloudDownloadId);
  const running = ["queued", "running"].includes(job.status);
  const remote = result.delivery ? deliveryMarkup(job) : "";
  if(result.localAvailable === false) return `<div class="job-actions">${remote}</div><p class="field-help">Saved to Google Drive. Temporary files removed.</p>`;
  if(running) return "";
  const retry = !result.delivery && !result.incomplete ? `<button class="button secondary" data-cloud-retry="${id}">Retry upload</button>` : "";
  return `${result.path ? `<code class="job-result-path">${escapeHtml(result.path)}</code>` : ""}<div class="job-actions">${remote}${retry}<button class="button ghost" data-cloud-discard="${id}">${result.delivery ? "Remove temporary files" : "Discard temporary download"}</button></div>`;
}

function jobResultMarkup(job) {
  if(job.result?.cloudDownloadId) return cloudDownloadMarkup(job);
  if(!job.result?.path) return "";
  const id = escapeHtml(job.id);
  return `<code class="job-result-path">${escapeHtml(job.result.path)}</code><div class="job-actions"><button class="button secondary" data-job-reveal="${id}">Open folder</button><button class="button secondary" data-job-share="${id}">Export / share</button>${deliveryMarkup(job)}<button class="button ghost" data-job-edit="${id}">Edit as new project</button></div>`;
}

async function retryCloudDownload(id) {
  try {
    const job = await api(`/api/downloads/pending/${encodeURIComponent(id)}/retry`, {method: "POST", body: "{}"});
    for(const [key, previous] of state.jobs) if(previous.result?.cloudDownloadId === id) state.jobs.delete(key);
    trackJob(job);
  } catch(error) { toast("Upload could not start", error.message, true); refreshConnections().catch(()=>{}); }
}

async function restoreCloudDownloads() {
  const {downloads} = await api("/api/downloads/pending");
  for(const result of downloads) {
    if([...state.jobs.values()].some(job => job.result?.cloudDownloadId === result.cloudDownloadId)) continue;
    const id = "pending-" + result.cloudDownloadId;
    state.jobs.set(id, {id, kind: "download", status: result.delivery ? "completed" : "failed", progress: result.delivery ? 100 : 80,
      message: result.delivery ? "Saved to Google Drive; remove temporary files" : result.incomplete ? "Source download interrupted — discard temporary files and download again" : "Upload pending — retry or discard the temporary download", result,
      createdAt: 0, log: []});
  }
  updateJobs();
}

async function wireDownloadDestinations() {
  updateDownloadDestination();
  $$("[data-download-destination]").forEach(button => button.addEventListener("click", async () => {
    downloadDestination = button.dataset.downloadDestination;
    localStorage.setItem("clipharbor-download-destination", downloadDestination);
    updateDownloadDestination();
    if(downloadDestination === "drive") {
      try { await refreshConnections(); } catch(error) { toast("Connections unavailable", error.message, true); }
    }
  }));
  $("#downloadConnectDrive").addEventListener("click", async () => {
    downloadConnecting = true; updateDownloadDestination();
    try {
      await connectGoogleAccount("drive", $("#downloadDriveFolderId").value.trim(), message => $("#downloadDriveStatus").textContent = message);
      toast("Google Drive connected", "Downloads can now go straight to your Drive.");
    } catch(error) { toast("Connection failed", error.message, true); }
    finally { downloadConnecting = false; updateDownloadDestination(); }
  });
  $("#downloadDisconnectDrive").addEventListener("click", async () => {
    try { await disconnectAccount("drive"); }
    catch(error) { toast("Could not disconnect", error.message, true); }
  });
  $("#jobsList").addEventListener("click", async event => {
    const retry = event.target.closest("[data-cloud-retry]");
    if(retry) return retryCloudDownload(retry.dataset.cloudRetry);
    const discard = event.target.closest("[data-cloud-discard]");
    if(!discard) return;
    const id = discard.dataset.cloudDiscard;
    const uploaded = [...state.jobs.values()].some(job => job.result?.cloudDownloadId === id && job.result.delivery);
    if(!uploaded && !confirm("Discard this temporary download? You will need to download it again to upload it to Drive.")) return;
    try {
      await api(`/api/downloads/pending/${encodeURIComponent(id)}`, {method: "DELETE"});
      for(const [key, job] of state.jobs) if(job.result?.cloudDownloadId === id) {
        if(job.result.delivery) job.result = {...job.result, path: null, token: null, localAvailable: false, cleanupPending: false};
        else state.jobs.delete(key);
      }
      updateJobs();
    } catch(error) { toast("Could not remove temporary files", error.message, true); }
  });
  try { await refreshConnections(); await restoreCloudDownloads(); }
  catch(error) { toast("Cloud destinations unavailable", error.message, true); }
}
document.addEventListener("DOMContentLoaded", wireDownloadDestinations);
