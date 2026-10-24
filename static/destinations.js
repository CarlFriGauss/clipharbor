/* Optional export destinations: no third-party scripts or SDKs. */
let exportSource = null;
let exportRequestId = "";
let exportSubmitting = false;
const retrySubmissions = new Set();
let exportDestination = localStorage.getItem("clipharbor-export-destination") || "local";
let connectionStatus = {};
let facebookBrowserStatus = {};
const destinationNames = {local:"This computer",drive:"Google Drive",youtube:"YouTube",x:"X",facebook:"Facebook Page",facebook_browser:"Facebook"};
function facebookBrowserSelected() { return exportDestination==="facebook"&&$("#facebookTarget").value!=="page_api"; }
async function refreshConnections() { connectionStatus=await api("/api/connections"); facebookBrowserStatus=await api("/api/browser/facebook").catch(()=>({})); updateDestination(); updateDownloadDestination(); }
function updateDestination() {
  if(!destinationNames[exportDestination]||exportDestination==="facebook_browser")exportDestination="local";
  $$("[data-destination]").forEach(b=>{const selected=b.dataset.destination===exportDestination;b.classList.toggle("selected",selected);b.setAttribute("aria-pressed",String(selected));});
  const remote=exportDestination!=="local", social=remote&&exportDestination!=="drive", connected=Boolean(connectionStatus[exportDestination]?.connected);
  const google=["drive","youtube"].includes(exportDestination), account=connectionStatus[exportDestination]||{}, signingIn=googleSignIns.has(exportDestination);
  const profile=facebookBrowserSelected();
  const automatic = profile && $("#facebookTarget").value === "profile_auto";
  $("#facebookBrowserSetup").classList.toggle("hidden",!automatic);
  $("#facebookAudienceField").classList.toggle("hidden",!automatic);
  $("#facebookBrowserStatus").textContent = facebookBrowserStatus.ready ? "Posting as " + facebookBrowserStatus.name : facebookBrowserStatus.configured ? "Open your connected Facebook companion browser" : "Connect the optional Facebook companion";
  $("#facebookTargetField").classList.toggle("hidden",exportDestination!=="facebook");
  $("#facebookProfileHelp").classList.toggle("hidden",!profile);
  $("#facebookProfileHelp").textContent=$("#facebookTarget").value==="page"?"ClipHarbor prepares your MP4 and opens Facebook. Switch to the Page you manage, choose Photo/video, attach the file, and post there. Your browser handles sign-in; no Facebook password or access token is saved in ClipHarbor.":"ClipHarbor prepares your MP4 and opens Facebook. Choose Photo/video, attach the file, and post there. Facebook does not allow apps to upload directly to personal profiles. Your browser handles sign-in; no Facebook password or access token is saved in ClipHarbor.";
  if(automatic) $("#facebookProfileHelp").textContent = "The companion opens your connected profile, attaches this video, inserts your post text, verifies the selected audience, and posts. Sign-in or an unrecognized Facebook screen stops the task. A confirmed success is required before ClipHarbor reports it as posted.";
  $("#connectionPanel").classList.toggle("hidden",!remote||profile);
  $("#googleConnection").classList.toggle("hidden",!["drive","youtube"].includes(exportDestination)||connected);
  $("#tokenConnection").classList.toggle("hidden",!["x","facebook"].includes(exportDestination)||connected);
  $("#facebookPageField").classList.toggle("hidden",exportDestination!=="facebook");
  $("#disconnectDestination").classList.toggle("hidden",!connected);
  $("#connectDestination").classList.toggle("hidden",connected);
  $("#connectDestination").textContent=google?"Sign in with Google":"Connect destination";
  $("#connectDestination").disabled=signingIn||(google&&!account.googleConfigured);
  $("#disconnectDestination").disabled=signingIn;
  $("#connectionStatus").textContent=destinationNames[exportDestination]+(signingIn?" — finish signing in in your browser":connected?" connected":account.needsReconnect?" — sign in again":" — connect to upload");
  $("#googleConnectionHelp").textContent=!account.googleConfigured?"Google sign-in is not available in this ClipHarbor build yet. The app publisher needs to enable it once; you do not need to create configuration files.":"Sign in with Google in your browser once. The connection is remembered securely on this computer. ClipHarbor never receives your Google password. Drive sign-in works in both Download and Export.";
  $("#tokenHelp").textContent=exportDestination==="x"?"Use an X user access token with media.write, tweet.write, tweet.read and users.read permissions. Your developer account must allow video uploads. App-only bearer tokens cannot publish.":"Use a Facebook Page access token with pages_manage_posts and pages_read_engagement permissions. Publishing is supported for Pages; personal profile uploads are unavailable through this API.";
  $("#tokenDocs").href=exportDestination==="x"?"https://docs.x.com/x-api/media/quickstart/media-upload-chunked":"https://developers.facebook.com/docs/video-api/guides/publishing/";
  $("#driveFolderField").classList.toggle("hidden",exportDestination!=="drive");
  $("#driveFolderName").textContent=connectionStatus.drive?.folderName||"ClipHarbor Exports";
  if(document.activeElement!==$("#driveFolderId"))$("#driveFolderId").value=connectionStatus.drive?.folderId||"";
  $("#socialDetails").classList.toggle("hidden",!social);
  $("#youtubeVisibilityField").classList.toggle("hidden",exportDestination!=="youtube");
  $("#publishField").classList.toggle("hidden",profile||!["x","facebook"].includes(exportDestination));
  $("#publishLabel").textContent=exportDestination==="x"?"Publish this video as an X post":"Publish this video to the Facebook Page (otherwise upload unpublished)";
  $("#exportDescription").maxLength=exportDestination==="x"?280:5000;
  $("#renderFields").classList.toggle("hidden",Boolean(exportSource));
  $("#exportSourceNote").classList.toggle("hidden",!exportSource);
  $("#exportDuration").classList.toggle("hidden",Boolean(exportSource));
  $("#deliveryTitleField").classList.toggle("hidden",!social||exportDestination==="x"||profile);
  $("#exportSourceNote").textContent=exportSource?"Upload the completed file directly: "+exportSource.media.name+". No additional render is needed.":"";
  $("#exportStorageNote").textContent=profile?"A local copy is kept. Finish the attachment, audience choice, and post in Facebook.":remote?"A local copy is kept. Uploads run in the background; a failed upload can be retried from Activity.":"Save the finished file to your computer.";
  $("#startExport").textContent=profile?(exportSource?"Prepare video & open Facebook":"Render & open Facebook"):exportSource?(remote?"Upload to "+destinationNames[exportDestination]:"Done"):(remote?"Render & export to "+destinationNames[exportDestination]:"Start render");
  $("#startExport").disabled=remote&&!profile&&!connected;
  if(automatic) {
    $("#startExport").textContent = exportSource ? "Post video to Facebook" : "Render & post to Facebook";
    $("#startExport").disabled = !facebookBrowserStatus.ready;
    $("#exportStorageNote").textContent = "A local copy is kept. Posting uses your connected browser profile and the audience selected above.";
  }
  $("#startExport").disabled = $("#startExport").disabled || exportSubmitting;
}
async function showExport(result=null) {
  exportSource=result;
  exportRequestId=crypto.randomUUID().replaceAll("-", "");
  $("#exportName").value=result?projectNameFromMedia(result.media.name):state.currentProjectName==="Untitled project"?"ClipHarbor export":state.currentProjectName;
  $("#exportPublish").checked=false;$("#deliveryTitle").value="";$("#exportDescription").value="";$("#youtubeVisibility").value="private";
  $("#facebookAudience").value="only_me";
  if(!result&&["x","youtube","facebook"].includes(exportDestination))$("#exportFormat").value=exportDestination==="x"?"x_mp4":"mp4";
  updateExportPresetUI();updateDestination();$("#exportDialog").showModal();
  try{await refreshConnections();}catch(error){toast("Connections unavailable",error.message,true);}
}
function deliveryPayload() {
  return {destination:facebookBrowserSelected()?"facebook_browser":exportDestination,deliveryOptions:{facebookTarget:$("#facebookTarget").value,audience:$("#facebookAudience").value,title:$("#deliveryTitle").value.trim()||$("#exportName").value.trim(),description:$("#exportDescription").value,folderId:$("#driveFolderId").value.trim(),privacy:$("#youtubeVisibility").value,publish:$("#exportPublish").checked}};
}
function deliveryMarkup(job) {
  if(job.result?.handoff)return '<button class="button secondary" data-facebook-ready="'+escapeHtml(job.id)+'">Continue in Facebook</button><span class="job-status">Video ready · finish posting in Facebook</span>';
  if(job.result?.browserPostingUncertain)return '<a class="button secondary" href="https://www.facebook.com/me" target="_blank" rel="noopener noreferrer">Check Facebook before trying again</a>';
  const d=job.result?.delivery;
  if(d)return '<a class="button secondary" href="'+escapeHtml(d.url)+'" target="_blank" rel="noopener noreferrer">Open in '+escapeHtml(destinationNames[d.provider])+'</a><span class="job-status">'+escapeHtml(d.visibility)+'</span>';
  if(job.status==="failed"&&job.result?.path&&job.deliveryRequest&&!job.retryJobId)return '<button class="button secondary" data-retry-upload="'+escapeHtml(job.id)+'"'+(retrySubmissions.has(job.id)?' disabled':'')+'>Retry upload</button>';
  return "";
}
async function retryDelivery(id) {
  const original=state.jobs.get(id);if(!original?.deliveryRequest||original.retryJobId||retrySubmissions.has(id)||original.result?.browserPostingUncertain)return;
  if(original.result?.cloudDownloadId)return retryCloudDownload(original.result.cloudDownloadId);
  retrySubmissions.add(id);updateJobs();
  try{const job=await api("/api/uploads",{method:"POST",body:JSON.stringify({token:original.result.token,...original.deliveryRequest,retryOf:id})});const parent=state.jobs.get(id)||original;parent.retryJobId=job.id;state.jobs.set(id,parent);job.deliveryRequest=original.deliveryRequest;trackJob(job);}
  catch(error){toast("Upload could not start",error.message,true);}
  finally{retrySubmissions.delete(id);updateJobs();}
}
const googleSignIns = new Set();
async function chooseDriveDestination() {
  if (googleSignIns.has("drive")) return toast("Google is already open", "Finish choosing your folder in the browser.");
  googleSignIns.add("drive"); updateDestination(); updateDownloadDestination();
  try {
    const job = await api("/api/connections/drive/folder-picker", {method:"POST", body:"{}"});
    toast("Choose a Drive folder", "Google's folder browser is opening. Select your destination there.");
    while (true) {
      const current = await api("/api/jobs/" + job.id);
      if (!["queued","running"].includes(current.status)) {
        if (current.status !== "completed") throw new Error(current.error || "No folder was selected.");
        await refreshConnections();
        $("#driveFolderId").value = connectionStatus.drive.folderId || "";
        $("#downloadDriveFolderId").value = connectionStatus.drive.folderId || "";
        localStorage.setItem("clipharbor-connections-changed",String(Date.now()));
        toast("Drive folder selected", connectionStatus.drive.folderName); break;
      }
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
  } catch(error) { toast("Folder selection did not finish", error.message, true); }
  finally { googleSignIns.delete("drive"); await refreshConnections().catch(()=>{}); }
}
async function connectGoogleAccount(provider, folderId, onProgress) {
  if(googleSignIns.has(provider))throw new Error("Google sign-in is already open. Finish it in your browser.");
  googleSignIns.add(provider);
  try {
    updateDestination();updateDownloadDestination();
    const job=await api("/api/connections/"+provider,{method:"POST",body:JSON.stringify({folderId})});
    while(true) {
      const current=await api("/api/jobs/"+job.id);
      onProgress(current.message);
      if(!["queued","running"].includes(current.status)) {
        if(current.status!=="completed")throw new Error(current.error||"Sign-in did not complete.");
        await refreshConnections();
        localStorage.setItem("clipharbor-connections-changed",String(Date.now()));
        return;
      }
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
  } finally { googleSignIns.delete(provider);await refreshConnections().catch(()=>{}); }
}
async function disconnectAccount(provider) {
  const result=await api("/api/connections/"+provider,{method:"DELETE"});
  await refreshConnections();
  localStorage.setItem("clipharbor-connections-changed",String(Date.now()));
  const message=result.disconnected?.includes("drive")?"Google Drive is disconnected in both Download and Export.":destinationNames[provider]+" is disconnected.";
  toast("Disconnected",result.warning||message,Boolean(result.warning));
}
async function connectDestination() {
  const provider=exportDestination,button=$("#connectDestination");button.disabled=true;
  try{
    if(["drive","youtube"].includes(provider)){
      await connectGoogleAccount(provider,provider==="drive"?$("#driveFolderId").value.trim():"",message=>$("#connectionStatus").textContent=message);
      toast("Connected",destinationNames[provider]+" is ready.");return;
    }
    await api("/api/connections/"+provider,{method:"POST",body:JSON.stringify({token:$("#destinationToken").value,pageId:$("#facebookPageId").value.trim()})});
    $("#destinationToken").value="";await refreshConnections();
  }catch(error){toast("Connection failed",error.message,true);}
  updateDestination();
}
function wireDestinations() {
  $("#exportChooseDriveFolder").addEventListener("click",chooseDriveDestination);
  $("#downloadChooseDriveFolder").addEventListener("click",chooseDriveDestination);
  const facebookTarget=localStorage.getItem("clipharbor-facebook-target");$("#facebookTarget").value=["profile_auto","profile","page","page_api"].includes(facebookTarget)?facebookTarget:"profile_auto";
  $("#facebookTarget").addEventListener("change",()=>{localStorage.setItem("clipharbor-facebook-target",$("#facebookTarget").value);$("#destinationToken").value="";$("#exportPublish").checked=false;updateDestination();});
  $$("[data-destination]").forEach(button=>button.addEventListener("click",()=>{
    exportDestination=button.dataset.destination;localStorage.setItem("clipharbor-export-destination",exportDestination);
    $("#destinationToken").value="";$("#exportPublish").checked=false;
    if(!exportSource&&["youtube","x","facebook"].includes(exportDestination))$("#exportFormat").value=exportDestination==="x"?"x_mp4":"mp4";
    updateExportPresetUI();updateDestination();
  }));
  $("#connectDestination").addEventListener("click",connectDestination);
  $("#disconnectDestination").addEventListener("click",async()=>{
    try{await disconnectAccount(exportDestination);}
    catch(error){toast("Could not disconnect",error.message,true);}
  });
  $("#shareResult").addEventListener("click",()=>{$("#completeDialog").close();showExport(state.lastResult);});
  $("#jobsList").addEventListener("click",event=>{
    const facebook=event.target.closest("[data-facebook-ready]");if(facebook)completeJob(state.jobs.get(facebook.dataset.facebookReady));
    const retry=event.target.closest("[data-retry-upload]");if(retry)retryDelivery(retry.dataset.retryUpload);
    const share=event.target.closest("[data-job-share]");if(share)showExport(state.jobs.get(share.dataset.jobShare)?.result);
  });
  window.addEventListener("storage",event=>{if(event.key==="clipharbor-connections-changed")refreshConnections().catch(()=>{});});
  window.addEventListener("focus",()=>refreshConnections().catch(()=>{}));
  $("#copyFacebookPath").addEventListener("click",()=>copyFacebookText(state.lastResult?.path,"Video location copied. In Facebook, choose Photo/video and paste it into the file picker."));
  $("#copyFacebookCaption").addEventListener("click",()=>copyFacebookText(state.lastResult?.handoff?.caption,"Post text copied. Paste it into your Facebook post."));
}

async function copyFacebookText(text, message) {
  try { await navigator.clipboard.writeText(text||"");$("#facebookCopyStatus").textContent=message; }
  catch(error) { $("#facebookCopyStatus").textContent="Copy was unavailable. Select the video location above and copy it, or use Open folder to find your video."; }
}
document.addEventListener("DOMContentLoaded",wireDestinations);
