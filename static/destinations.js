/* Optional export destinations: no third-party scripts or SDKs. */
let exportSource = null;
let exportDestination = localStorage.getItem("clipharbor-export-destination") || "local";
let connectionStatus = {};
const destinationNames = {local:"This computer",drive:"Google Drive",youtube:"YouTube",x:"X",facebook:"Facebook Page"};
async function refreshConnections() { connectionStatus=await api("/api/connections"); updateDestination(); updateDownloadDestination(); }
function updateDestination() {
  if(!destinationNames[exportDestination])exportDestination="local";
  $$("[data-destination]").forEach(b=>{const selected=b.dataset.destination===exportDestination;b.classList.toggle("selected",selected);b.setAttribute("aria-pressed",String(selected));});
  const remote=exportDestination!=="local", social=remote&&exportDestination!=="drive", connected=Boolean(connectionStatus[exportDestination]?.connected);
  const google=["drive","youtube"].includes(exportDestination), account=connectionStatus[exportDestination]||{}, signingIn=googleSignIns.has(exportDestination);
  $("#connectionPanel").classList.toggle("hidden",!remote);
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
  $("#publishField").classList.toggle("hidden",!["x","facebook"].includes(exportDestination));
  $("#publishLabel").textContent=exportDestination==="x"?"Publish this video as an X post":"Publish this video to the Facebook Page (otherwise upload unpublished)";
  $("#exportDescription").maxLength=exportDestination==="x"?280:5000;
  $("#renderFields").classList.toggle("hidden",Boolean(exportSource));
  $("#exportSourceNote").classList.toggle("hidden",!exportSource);
  $("#exportDuration").classList.toggle("hidden",Boolean(exportSource));
  $("#deliveryTitleField").classList.toggle("hidden",!social||exportDestination==="x");
  $("#exportSourceNote").textContent=exportSource?"Upload the completed file directly: "+exportSource.media.name+". No additional render is needed.":"";
  $("#exportStorageNote").textContent=remote?"A local copy is kept. Uploads run in the background; a failed upload can be retried from Activity.":"Save the finished file to your computer.";
  $("#startExport").textContent=exportSource?(remote?"Upload to "+destinationNames[exportDestination]:"Done"):(remote?"Render & export to "+destinationNames[exportDestination]:"Start render");
  $("#startExport").disabled=remote&&!connected;
}
async function showExport(result=null) {
  exportSource=result;
  $("#exportName").value=result?projectNameFromMedia(result.media.name):state.currentProjectName==="Untitled project"?"ClipHarbor export":state.currentProjectName;
  $("#exportPublish").checked=false;$("#deliveryTitle").value="";$("#exportDescription").value="";$("#youtubeVisibility").value="private";
  if(!result&&["x","youtube","facebook"].includes(exportDestination))$("#exportFormat").value=exportDestination==="x"?"x_mp4":"mp4";
  updateExportPresetUI();updateDestination();$("#exportDialog").showModal();
  try{await refreshConnections();}catch(error){toast("Connections unavailable",error.message,true);}
}
function deliveryPayload() {
  return {destination:exportDestination,deliveryOptions:{title:$("#deliveryTitle").value.trim()||$("#exportName").value.trim(),description:$("#exportDescription").value,folderId:$("#driveFolderId").value.trim(),privacy:$("#youtubeVisibility").value,publish:$("#exportPublish").checked}};
}
function deliveryMarkup(job) {
  const d=job.result?.delivery;
  if(d)return '<a class="button secondary" href="'+escapeHtml(d.url)+'" target="_blank" rel="noopener noreferrer">Open in '+escapeHtml(destinationNames[d.provider])+'</a><span class="job-status">'+escapeHtml(d.visibility)+'</span>';
  if(job.status==="failed"&&job.result?.path&&job.deliveryRequest)return '<button class="button secondary" data-retry-upload="'+escapeHtml(job.id)+'">Retry upload</button>';
  return "";
}
async function retryDelivery(id) {
  const original=state.jobs.get(id);if(!original?.deliveryRequest)return;
  if(original.result?.cloudDownloadId)return retryCloudDownload(original.result.cloudDownloadId);
  try{const job=await api("/api/uploads",{method:"POST",body:JSON.stringify({token:original.result.token,...original.deliveryRequest})});job.deliveryRequest=original.deliveryRequest;trackJob(job);}
  catch(error){toast("Upload could not start",error.message,true);}
}
const googleSignIns = new Set();
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
    const retry=event.target.closest("[data-retry-upload]");if(retry)retryDelivery(retry.dataset.retryUpload);
    const share=event.target.closest("[data-job-share]");if(share)showExport(state.jobs.get(share.dataset.jobShare)?.result);
  });
  window.addEventListener("storage",event=>{if(event.key==="clipharbor-connections-changed")refreshConnections().catch(()=>{});});
  window.addEventListener("focus",()=>refreshConnections().catch(()=>{}));
}
document.addEventListener("DOMContentLoaded",wireDestinations);
