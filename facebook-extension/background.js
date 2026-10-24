import {facebookPage} from "./page.js";
const HOST="com.clipharbor.downloader";
let activeTask=null, attachedTab=null;
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function native(action,fields={}) {
  let result;
  try { result=await chrome.runtime.sendNativeMessage(HOST,{protocol:1,action,...fields}); }
  catch { throw new Error("Install ClipHarbor 0.9.0 or newer and reopen the app. Its local bridge is unavailable."); }
  if(!result?.ok) throw new Error(result?.error||"ClipHarbor is unavailable.");
  return result;
}
async function identifier() {
  const {browserId}=await chrome.storage.local.get("browserId");
  if(browserId) return browserId;
  const value=crypto.randomUUID().replaceAll("-",""); await chrome.storage.local.set({browserId:value}); return value;
}
async function page(tabId,action,fields={}) {
  const tab=await chrome.tabs.get(tabId);
  if(tab.status === "loading" && (!tab.url || tab.url.startsWith("https://www.facebook.com/"))) return {waiting:"Loading Facebook"};
  if(!tab.url?.startsWith("https://www.facebook.com/")) throw new Error("Posting stopped because the tab left Facebook.");
  const [response]=await chrome.scripting.executeScript({target:{tabId},func:facebookPage,args:[action,fields]});
  if(response.result?.error) throw new Error(response.result.error);
  return response.result||{};
}
async function report(task,phase,message,url="") {
  await native("browserReport",{browserId:await identifier(),taskId:task.id,lease:task.lease,phase,message,url});
  await chrome.storage.local.set({message});
}
async function until(task,tabId,action,done,fields={},timeout=90000) {
  const end=Date.now()+timeout;
  let heartbeat=0;
  while(Date.now()<end) {
    const {enabled}=await chrome.storage.local.get("enabled");
    if(!enabled) throw new Error("Browser posting was stopped by the user.");
    const result=await page(tabId,action,fields);
    if(await done(result)) return result;
    if(Date.now()-heartbeat>10000) { await report(task,"working",result.waiting||"Working in Facebook"); heartbeat=Date.now(); }
    await wait(1000);
  }
  throw new Error("Facebook's expected controls did not become available. Check the open Facebook tab; the task will not be repeated automatically.");
}
async function run(task) {
  activeTask=task;
  let tabId=null;
  try {
    const tab=await chrome.tabs.create({url:task.profileUrl,active:true}); tabId=tab.id;
    await until(task,tabId,"open",result=>result.opened,{},60000);
    await chrome.debugger.attach({tabId},"1.3"); attachedTab=tabId;
    const marker=crypto.randomUUID().replaceAll("-","");
    const prepared=await until(task,tabId,"prepare",result=>result.fileSelector,{marker,caption:task.caption});
    const {root}=await chrome.debugger.sendCommand({tabId},"DOM.getDocument",{});
    const {nodeId}=await chrome.debugger.sendCommand({tabId},"DOM.querySelector",{nodeId:root.nodeId,selector:prepared.fileSelector});
    if(!nodeId) throw new Error("The video input changed before attachment. Nothing was posted.");
    await chrome.debugger.sendCommand({tabId},"DOM.setFileInputFiles",{nodeId,files:[task.path]});
    await report(task,"working","Video attached; preparing your caption");
    let inserted=false;
    await until(task,tabId,"caption",async result=>{
      if(result.insertText && !inserted && task.caption) {
        await chrome.debugger.sendCommand({tabId},"Input.insertText",{text:task.caption}); inserted=true; return false;
      }
      return result.captionReady;
    },{caption:task.caption},600000);
    await until(task,tabId,"audience",result=>result.audienceReady,{audience:task.audience},90000);
    await report(task,"audience_verified","Requested audience verified");
    // Persist intent before a single Post click. Loss of the response after this
    // point is an uncertain result; neither companion nor desktop resubmits it.
    await report(task,"posting","Publishing to Facebook");
    await until(task,tabId,"publish",result=>result.clicked,{caption:task.caption,audience:task.audience,marker},600000);
    const confirmation=await until(task,tabId,"confirm",result=>result.confirmed,{profileUrl:task.profileUrl,marker},180000);
    await report(task,"completed","Facebook confirmed the post",confirmation.url);
    await chrome.action.setBadgeText({text:"✓"});
  } catch(error) {
    try { await report(task,"failed",error.message); } catch {}
    await chrome.storage.local.set({message:error.message});
    await chrome.action.setBadgeText({text:"!"});
  } finally {
    if(attachedTab!==null) { try { await chrome.debugger.detach({tabId:attachedTab}); } catch {} }
    attachedTab=null; activeTask=null;
  }
}
let polling=false;
async function poll() {
  if(polling||activeTask) return;
  const {enabled}=await chrome.storage.local.get("enabled"); if(!enabled) return;
  polling=true;
  try {
    const {task}=await native("browserPoll",{browserId:await identifier()});
    if(task) await run(task);
  } catch(error) { await chrome.storage.local.set({message:error.message}); }
  finally { polling=false; }
}
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==="facebook")poll();});
async function resume() { const {enabled}=await chrome.storage.local.get("enabled"); if(enabled) { await chrome.alarms.create("facebook",{periodInMinutes:.5}); poll(); } }
chrome.runtime.onInstalled.addListener(resume);
chrome.runtime.onStartup.addListener(resume);
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if(sender.id!==chrome.runtime.id||sender.tab) return false;
  (async()=>{
    if(message.action==="status") return chrome.storage.local.get(["enabled","name","message"]);
    if(message.action==="disable") {
      await chrome.storage.local.set({enabled:false,message:"Browser posting stopped."});
      await chrome.alarms.clear("facebook");
      return {enabled:false,message:"Browser posting stopped. Local files and account sign-in were kept."};
    }
    if(message.action==="connect") {
      const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
      const profile=await page(tab.id,"profile");
      await native("browserRegister",{browserId:await identifier(),...profile});
      await chrome.storage.local.set({enabled:true,name:profile.name,message:"Ready. In ClipHarbor Export choose My profile · post through browser companion."});
      await chrome.alarms.create("facebook",{periodInMinutes:.5}); poll();
      return {enabled:true,name:profile.name,message:"Connected. Export from ClipHarbor to post your chosen video and caption."};
    }
    throw new Error("Unknown companion action.");
  })().then(result=>reply({ok:true,...result}),error=>reply({ok:false,error:error.message}));
  return true;
});
export {run as runFacebookTask};
