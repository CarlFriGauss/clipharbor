/* Native panel resizing and fullscreen; no UI framework or media processing. */
const editorLayout = {mediaOpen:true,mediaWidth:220,propertiesWidth:260,previewRatio:.6};
const EDITOR_LAYOUT_KEY = "clipharbor-editor-layout-v1";
function saveEditorLayout() {
  try { localStorage.setItem(EDITOR_LAYOUT_KEY,JSON.stringify(editorLayout)); } catch (_) { /* Resizing also works without browser storage. */ }
}
function editorPanelWidths(width, media, properties, open) {
  const mediaMin=open?140:0,propertiesMin=180,budget=Math.max(mediaMin+propertiesMin,width-44-(open?20:10)-160);
  let left=open?Math.max(mediaMin,Math.min(420,Number(media)||220)):0,right=Math.max(propertiesMin,Math.min(420,Number(properties)||260));
  if(left+right>budget){const extra=left+right-mediaMin-propertiesMin,ratio=Math.max(0,(budget-mediaMin-propertiesMin)/Math.max(1,extra));left=mediaMin+(left-mediaMin)*ratio;right=propertiesMin+(right-propertiesMin)*ratio;}
  return {media:Math.round(left),properties:Math.round(right)};
}
function editorAvailableHeight() {
  const view=$("#editorView"),toolbar=$(".editor-toolbar"),style=getComputedStyle(view),toolbarStyle=getComputedStyle(toolbar);
  return Math.max(220,view.clientHeight-toolbar.offsetHeight-(parseFloat(toolbarStyle.marginBottom)||0)-(parseFloat(style.paddingTop)||0)-(parseFloat(style.paddingBottom)||0)-$("#panelDivider").offsetHeight);
}
function applyEditorLayout() {
  const shell=$("#editorShell");if(!shell.clientWidth||!$("#editorView").classList.contains("active"))return;
  const widths=editorPanelWidths(shell.clientWidth,editorLayout.mediaWidth,editorLayout.propertiesWidth,editorLayout.mediaOpen);
  shell.style.setProperty("--media-width",widths.media+"px");shell.style.setProperty("--properties-width",widths.properties+"px");
  shell.classList.toggle("media-collapsed",!editorLayout.mediaOpen);$("#mediaPanel").hidden=!editorLayout.mediaOpen;$("#mediaDivider").hidden=!editorLayout.mediaOpen;
  const toggle=$("#toggleMediaPanel");toggle.setAttribute("aria-pressed",String(editorLayout.mediaOpen));toggle.setAttribute("aria-expanded",String(editorLayout.mediaOpen));toggle.setAttribute("aria-label",editorLayout.mediaOpen?"Hide media panel":"Show media panel");
  $("#mediaDivider").setAttribute("aria-valuenow",String(widths.media));$("#propertiesDivider").setAttribute("aria-valuenow",String(widths.properties));
  const available=editorAvailableHeight(),timelineMin=Math.max(120,$(".timeline-toolbar").offsetHeight+65),height=Math.max(100,Math.min(available-timelineMin,available*editorLayout.previewRatio));
  $("#editorView").style.setProperty("--timeline-min-height",timelineMin+"px");$("#editorView").style.setProperty("--preview-height",Math.round(height)+"px");$("#panelDivider").setAttribute("aria-valuenow",String(Math.round(height)));$("#panelDivider").setAttribute("aria-valuemax",String(Math.round(available-timelineMin)));
  scheduleWaveforms();
}
function wireEditorLayout() {
  try { const saved=JSON.parse(localStorage.getItem(EDITOR_LAYOUT_KEY));if(saved&&typeof saved==="object"){if(typeof saved.mediaOpen==="boolean")editorLayout.mediaOpen=saved.mediaOpen;for(const key of ["mediaWidth","propertiesWidth"]){if(Number.isFinite(saved[key]))editorLayout[key]=Math.max(key==="mediaWidth"?140:180,Math.min(420,saved[key]));}if(Number.isFinite(saved.previewRatio))editorLayout.previewRatio=Math.max(.1,Math.min(.9,saved.previewRatio));} } catch (_) { /* Ignore malformed or unavailable preferences. */ }
  $("#toggleMediaPanel").addEventListener("click",()=>{editorLayout.mediaOpen=!editorLayout.mediaOpen;applyEditorLayout();saveEditorLayout();});
  function wireDivider(selector,axis,getValue,setValue,direction){
    const divider=$(selector);let drag=null;
    divider.addEventListener("pointerdown",event=>{if(event.button!==0)return;event.preventDefault();drag={position:axis==="x"?event.clientX:event.clientY,value:getValue()};divider.setPointerCapture(event.pointerId);});
    divider.addEventListener("pointermove",event=>{if(!drag)return;setValue(drag.value+direction*((axis==="x"?event.clientX:event.clientY)-drag.position));applyEditorLayout();});
    const finish=()=>{if(drag){drag=null;saveEditorLayout();}};divider.addEventListener("pointerup",finish);divider.addEventListener("pointercancel",finish);divider.addEventListener("lostpointercapture",finish);
    divider.addEventListener("keydown",event=>{const keys=axis==="x"?{ArrowLeft:-1,ArrowRight:1}:{ArrowUp:-1,ArrowDown:1};if(keys[event.key]){event.preventDefault();setValue(getValue()+direction*keys[event.key]*(event.shiftKey?40:20));applyEditorLayout();saveEditorLayout();}});
  }
  function resizeSide(key,value){
    const shell=$("#editorShell"),other=key==="mediaWidth"?$("#propertiesPanel").getBoundingClientRect().width:editorLayout.mediaOpen?$("#mediaPanel").getBoundingClientRect().width:0;
    const max=Math.min(420,shell.clientWidth-44-(editorLayout.mediaOpen?20:10)-160-other);
    editorLayout[key]=Math.max(key==="mediaWidth"?140:180,Math.min(max,value));
  }
  wireDivider("#mediaDivider","x",()=>$("#mediaPanel").getBoundingClientRect().width,value=>resizeSide("mediaWidth",value),1);
  wireDivider("#propertiesDivider","x",()=>$("#propertiesPanel").getBoundingClientRect().width,value=>resizeSide("propertiesWidth",value),-1);
  wireDivider("#panelDivider","y",()=>$("#editorShell").getBoundingClientRect().height,value=>{const available=editorAvailableHeight(),minimum=Math.max(120,$(".timeline-toolbar").offsetHeight+65);editorLayout.previewRatio=Math.max(100,Math.min(available-minimum,value))/available;},1);
  const panel=$("#previewPanel"),fullscreen=$("#previewFullscreen");
  const updateFullscreen=()=>{const active=document.fullscreenElement===panel||panel.classList.contains("preview-expanded");fullscreen.textContent=active?"×":"⛶";fullscreen.setAttribute("aria-label",active?"Exit preview fullscreen":"Enter preview fullscreen");fullscreen.title=active?"Exit fullscreen (Esc)":"Fullscreen preview";};
  fullscreen.addEventListener("click",async()=>{
    if(panel.classList.contains("preview-expanded")){panel.classList.remove("preview-expanded");updateFullscreen();return;}
    if(document.fullscreenElement===panel){await document.exitFullscreen();return;}
    try{if(!panel.requestFullscreen)throw new Error("Fullscreen unavailable");await panel.requestFullscreen();}
    catch(_){panel.classList.add("preview-expanded");} // Keep preview expansion available when the browser denies native fullscreen.
    updateFullscreen();
  });
  document.addEventListener("fullscreenchange",updateFullscreen);
  document.addEventListener("keydown",event=>{if(event.key==="Escape"&&panel.classList.contains("preview-expanded")){event.preventDefault();event.stopImmediatePropagation();panel.classList.remove("preview-expanded");updateFullscreen();}});
  new ResizeObserver(applyEditorLayout).observe($("#editorView"));
  window.addEventListener("resize",applyEditorLayout);applyEditorLayout();
}
