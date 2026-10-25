const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

class Element {
  value='';disabled=false;hidden=false;textContent='';listeners={};children=[];
  classList={toggle:(name,value)=>{this[name]=value;},remove(){}};
  set innerHTML(value){this.html=value;this.value='';}
  get innerHTML(){return this.html;}
  get selectedOptions(){return [{dataset:{label:'Spanish'},textContent:'Spanish'}];}
  replaceChildren(...children){this.children=children;this.value=children[0]?.value||'';}
  addEventListener(name,callback){this.listeners[name]=callback;}
}
const info={title:'Source',site:'Facebook',audioTracks:[{formatId:'en',language:'en',label:'en',original:true},{formatId:'es',language:'es',label:'es',dubbed:true}],
  subtitleTracks:[{language:'en',label:'English',source:'manual'},{language:'fr',label:'French',source:'automatic',automatic:true,translated:true}]};
const elementMap=new Map();
const element=id=>{if(!elementMap.has(id))elementMap.set(id,new Element());return elementMap.get(id);};
const app=fs.readFileSync('static/app.js','utf8');
let submitted;
const state={inspected:structuredClone(info),inspectedUrl:'https://example.test/video',inspectedCookie:''};
const ctx=vm.createContext({state,Intl,navigator:{language:'en'},$:id=>element(id),escapeHtml:value=>String(value).replaceAll('<','&lt;'),
  api:async(path,options)=>{submitted=JSON.parse(options.body);return {id:'job'};},downloadDeliveryPayload:()=>({destination:'local'}),
  connectionStatus:{},updateDownloadDestination(){},trackJob(){},toast(){},setView(){},downloadStarting:false});
vm.runInContext(app.slice(app.indexOf('function renderAudioTracks('),app.indexOf('function projectNameFromMedia(')),ctx);
vm.runInContext(app.slice(app.indexOf('async function startDownload('),app.indexOf('function trackJob(')),ctx);
element('#formatSelect').value='mp4';element('#urlInput').value=state.inspectedUrl;element('#cookiePath').value='';element('#outputPath').value='/downloads';
element('#subtitleModeSelect').value='burn';element('#burnSizeSelect').value='source';

(async()=>{
  ctx.renderSourceTracks(info);
  assert.equal(element('#subtitleTrackField').hidden,false);
  assert.equal(element('#subtitleTrackSelect').value,'','Inspection must default to None');
  assert.match(element('#subtitleTrackSelect').innerHTML,/French.*auto-translated/);
  await ctx.startDownload();assert.equal(submitted.subtitleLanguage,null,'None must not select track index zero');
  element('#subtitleTrackSelect').value='0';await ctx.startDownload();
  assert.equal(submitted.subtitleLanguage,'en');assert.equal(submitted.subtitleSource,'manual');
  assert.equal(submitted.subtitleMode,'burn');assert.equal(submitted.burnSize,'source');
  ctx.updateSubtitleFormat();assert.equal(element('#subtitleModeField').hidden,false);assert.equal(element('#burnSizeField').hidden,false);
  element('#subtitleModeSelect').value='embed';ctx.updateSubtitleFormat();assert.equal(element('#burnSizeField').hidden,true);
  await ctx.startDownload();assert.equal(submitted.subtitleMode,'embed');
  element('#subtitleTrackSelect').value='1';await ctx.startDownload();
  assert.equal(submitted.subtitleLanguage,'fr');assert.equal(submitted.subtitleSource,'automatic');
  element('#formatSelect').value='mp3';ctx.updateSubtitleFormat();await ctx.startDownload();
  assert.equal(element('#subtitleTrackSelect').disabled,true);assert.equal(submitted.subtitleLanguage,null);
  element('#formatSelect').value='mp4';ctx.updateSubtitleFormat();
  element('#urlInput').value='https://example.test/another';await ctx.startDownload();
  assert.equal(submitted.subtitleLanguage,null);assert.equal(submitted.audioFormatId,null,'A different source must not inherit audio choices');
  ctx.renderSourceTracks({});assert.equal(element('#subtitleTrackField').hidden,true);
  assert.equal(ctx.subtitleDescription({language:'ar-orig',sourceLanguage:'ar',originalCaption:true}),'captions for Arabic audio');
  assert.equal(ctx.subtitleDescription({language:'ar',sourceLanguage:'en',translated:true}),'translated from English');

  // Run the popup's actual handlers to verify the same behavior across the native bridge.
  elementMap.clear();let messages=[];
  const chrome={runtime:{sendMessage:async request=>{messages.push(request);return request.action==='status'?{ok:true,version:'test',drive:{},settings:{destination:'local',outputFormat:'mp4'}}:
    request.action==='inspect'?{ok:true,info:structuredClone(info)}:request.action==='jobs'?{ok:true,downloads:[]}:{ok:true,job:{id:'test'}};}},
    storage:{local:{get:async()=>({})}},tabs:{query:async()=>[{id:1,url:'https://example.test/video'}]},scripting:{executeScript:async()=>[{result:[]}]}};
  const popup=vm.createContext({chrome,Intl,navigator:{language:'en'},$:element,cleanUrl:url=>url||null,discoverMedia(){},
    ACTIVE:new Set(['queued','running']),Option:function(text,value){this.textContent=text;this.value=value;},setInterval(){},document:{getElementById:element}});
  const code=fs.readFileSync('browser-extension/popup.js','utf8').replace(/^import[^\n]*\n/,'').replace('init(); setInterval(refresh, 3000);','');
  vm.runInContext(code,popup);await popup.init();await element('inspect').listeners.click();
  element('subtitleMode').value='burn';element('burnSize').value='source';
  assert.equal(element('subtitleField').hidden,false);assert.equal(element('subtitleTrack').value,'');
  element('subtitleTrack').value='1';element('audioTrack').value='es';
  await element('downloadForm').listeners.submit({preventDefault(){}});
  assert.equal(messages.findLast(x=>x.action==='download').subtitleLanguage,'fr');
  assert.equal(messages.findLast(x=>x.action==='download').audioFormatId,'es');
  assert.equal(messages.findLast(x=>x.action==='download').subtitleMode,'burn');assert.equal(messages.findLast(x=>x.action==='download').burnSize,'source');
  element('format').value='mp3';popup.update();await element('downloadForm').listeners.submit({preventDefault(){}});
  assert.equal(messages.findLast(x=>x.action==='download').subtitleLanguage,null);
  element('url').value='https://example.test/new';element('url').listeners.input();popup.update();
  await element('downloadForm').listeners.submit({preventDefault(){}});
  assert.equal(messages.findLast(x=>x.action==='download').audioFormatId,null);
  assert.equal(popup.subtitleDescription({language:'ar-orig',sourceLanguage:'ar',originalCaption:true}),'captions for Arabic audio');
  assert.equal(popup.subtitleDescription({language:'ar',sourceLanguage:'en',translated:true}),'translated from English');

  state.jobs=new Map([['active',{id:'active',kind:'download',status:'running',progress:86,message:'Saving MP4',canCancel:true}]]);
  ctx.jobResultMarkup=()=>'';
  vm.runInContext(app.slice(app.indexOf('function updateJobs('),app.indexOf('async function revealResult(')),ctx);
  ctx.updateJobs();assert.match(element('#jobsList').innerHTML,/Cancel download/);
  state.jobs.get('active').cancelRequested=true;state.jobs.get('active').canCancel=false;
  ctx.updateJobs();assert.match(element('#jobsList').innerHTML,/disabled>Cancelling/);
  state.jobs.get('active').status='cancelled';ctx.updateJobs();assert.doesNotMatch(element('#jobsList').innerHTML,/data-cancel-job/);
  console.log('App and popup subtitle selection, None, audio-only formats, and stale-source resets passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
