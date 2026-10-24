import assert from "node:assert/strict";
let enabled=true, inserted=false, publishCount=0, rejectedPosting=false;
let events=[];
globalThis.chrome={
 storage:{local:{get:async key=>key==="browserId"?{browserId:"a".repeat(32)}:{enabled},set:async()=>{}}},
 runtime:{sendNativeMessage:async(host,message)=>{
   events.push(message.phase||message.action);
   if(message.phase==="posting"&&rejectedPosting) throw new Error("Desktop stopped");
   return {ok:true};
 },onInstalled:{addListener(){}},onStartup:{addListener(){}},onMessage:{addListener(){}}},
 tabs:{create:async()=>({id:1}),get:async()=>({url:"https://www.facebook.com/Example.Person",status:"complete"})},
 scripting:{executeScript:async options=>{
  const [action]=options.args;events.push(action);
  const result=action==="open"?{opened:true}:action==="prepare"?{fileSelector:'input[data-clipharbor-file="one"]'}:
    action==="caption"?(inserted?{captionReady:true}:{insertText:true}):action==="audience"?{audienceReady:true}:
    action==="publish"?(()=>{publishCount++;return {clicked:true};})():action==="confirm"?{confirmed:true,url:"https://www.facebook.com/Example.Person"}:{};
  return [{result}];
 }},
 debugger:{attach:async()=>{},detach:async()=>{},sendCommand:async(target,method,params)=>{
   if(method==="DOM.getDocument")return {root:{nodeId:1}};
   if(method==="DOM.querySelector")return {nodeId:2};
   if(method==="DOM.setFileInputFiles")assert.deepEqual(params.files,["D:/exports/chosen.mp4"]);
   if(method==="Input.insertText"){assert.equal(params.text,"Chosen caption");inserted=true;}
   return {};
 }},
 alarms:{onAlarm:{addListener(){}},create:async()=>{},clear:async()=>{}},
 action:{setBadgeText:async()=>{}}
};
const {runFacebookTask}=await import("../facebook-extension/background.js");
const task={id:"task",lease:"lease",path:"D:/exports/chosen.mp4",caption:"Chosen caption",audience:"only_me",profileUrl:"https://www.facebook.com/Example.Person"};
await runFacebookTask(task);
assert.equal(publishCount,1);
assert.ok(events.indexOf("audience_verified")<events.indexOf("posting")&&events.indexOf("posting")<events.indexOf("publish"));
assert.ok(events.includes("completed"));
events=[];publishCount=0;rejectedPosting=true;
await runFacebookTask(task);
assert.equal(publishCount,0,"Desktop permission/intent acknowledgement must precede any Post click");
assert.ok(!events.includes("completed"));
console.log("Facebook file scope, caption, audience acknowledgement, single Post click, and offline-stop checks passed.");
