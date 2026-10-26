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
  append(...children){this.children.push(...children);}
  setAttribute(name,value){this[name]=value;}
  addEventListener(name,callback){this.listeners[name]=callback;}
}
const info={title:'Source',site:'Facebook',audioTracks:[{formatId:'en',language:'en',label:'en',original:true},{formatId:'es',language:'es',label:'es',dubbed:true}],
  subtitleTracks:[{language:'en',label:'English',source:'manual'},{language:'fr',label:'French',source:'automatic',automatic:true,translated:true}]};
const elementMap=new Map();
const element=id=>{if(!elementMap.has(id))elementMap.set(id,new Element());return elementMap.get(id);};
const app=fs.readFileSync('static/app.js','utf8');
const template=fs.readFileSync('templates/index.html','utf8'),popupHtml=fs.readFileSync('browser-extension/popup.html','utf8');
function htmlDefault(html,id){
  const select=html.match(new RegExp(`<select\\b[^>]*\\bid="${id}"[^>]*>([\\s\\S]*?)</select>`));
  assert.ok(select,`Missing select ${id}`);
  const options=[...select[1].matchAll(/<option\b([^>]*)>/g)];
  const selected=options.find(option=>/\bselected(?:\s|=|$)/.test(option[1]))||options[0];
  return selected[1].match(/\bvalue="([^"]*)"/)[1];
}
assert.equal(htmlDefault(template,'formatSelect'),'original');assert.equal(htmlDefault(popupHtml,'format'),'original');
assert.equal(htmlDefault(template,'subtitleModeSelect'),'embed');assert.equal(htmlDefault(popupHtml,'subtitleMode'),'embed');
assert.equal(htmlDefault(template,'burnSizeSelect'),'source');assert.equal(htmlDefault(popupHtml,'burnSize'),'source');
let submitted;
const state={inspected:structuredClone(info),inspectedUrl:'https://example.test/video',inspectedCookie:''};
const ctx=vm.createContext({state,Intl,navigator:{language:'en'},$:id=>element(id),escapeHtml:value=>String(value).replaceAll('<','&lt;'),
  api:async(path,options)=>{submitted=JSON.parse(options.body);return {id:'job'};},downloadDeliveryPayload:()=>({destination:'local'}),
  connectionStatus:{},updateDownloadDestination(){},trackJob(){},toast(){},setView(){},downloadStarting:false});
vm.runInContext(app.slice(app.indexOf('function renderAudioTracks('),app.indexOf('function projectNameFromMedia(')),ctx);
vm.runInContext(app.slice(app.indexOf('async function startDownload('),app.indexOf('function trackJob(')),ctx);
element('#formatSelect').value='mp4';element('#urlInput').value=state.inspectedUrl;element('#cookiePath').value='';element('#outputPath').value='/downloads';
element('#subtitleModeSelect').value=htmlDefault(template,'subtitleModeSelect');element('#burnSizeSelect').value='source';

(async()=>{
  ctx.renderSourceTracks(info);
  assert.equal(element('#subtitleTrackField').hidden,false);
  assert.equal(element('#subtitleTrackSelect').value,'','Inspection must default to None');
  assert.match(element('#subtitleTrackSelect').innerHTML,/French.*auto-translated/);
  await ctx.startDownload();assert.equal(submitted.subtitleLanguage,null,'None must not select track index zero');
  element('#subtitleTrackSelect').value='0';await ctx.startDownload();
  assert.equal(submitted.subtitleLanguage,'en');assert.equal(submitted.subtitleSource,'manual');
  assert.equal(submitted.subtitleMode,'embed');assert.equal(submitted.burnSize,'source');
  assert.equal(submitted.burnAcknowledged,false);
  ctx.updateSubtitleFormat();assert.equal(element('#subtitleModeField').hidden,false);assert.equal(element('#burnSizeField').hidden,true);
  assert.match(element('#subtitleTrackHelp').textContent,/without encoding the video or chosen audio again/);
  element('#subtitleModeSelect').value='burn';ctx.updateSubtitleFormat();assert.equal(element('#burnSizeField').hidden,false);
  assert.match(element('#subtitleTrackHelp').textContent,/does not preserve.*original compressed quality/);
  await ctx.startDownload();assert.equal(submitted.subtitleMode,'burn','Encoding requires an explicit burn choice');
  assert.equal(submitted.burnAcknowledged,true);
  element('#subtitleModeSelect').value='embed';ctx.updateSubtitleFormat();assert.equal(element('#burnSizeField').hidden,true);
  await ctx.startDownload();assert.equal(submitted.subtitleMode,'embed');
  assert.equal(submitted.burnAcknowledged,false);
  element('#subtitleTrackSelect').value='1';await ctx.startDownload();
  assert.equal(submitted.subtitleLanguage,'fr');assert.equal(submitted.subtitleSource,'automatic');
  element('#formatSelect').value='mp3';ctx.updateSubtitleFormat();await ctx.startDownload();
  assert.equal(element('#subtitleTrackSelect').disabled,true);assert.equal(submitted.subtitleLanguage,null);
  element('#formatSelect').value='mp4';ctx.updateSubtitleFormat();
  element('#urlInput').value='https://example.test/another';await ctx.startDownload();
  assert.equal(submitted.subtitleLanguage,null);assert.equal(submitted.audioFormatId,null,'A different source must not inherit audio choices');
  element('#subtitleModeSelect').value='burn';ctx.renderSourceTracks({});assert.equal(element('#subtitleTrackField').hidden,true);
  assert.equal(element('#subtitleModeSelect').value,'embed','A new source must not inherit an earlier burn choice');
  assert.equal(ctx.subtitleDescription({language:'ar-orig',sourceLanguage:'ar',originalCaption:true}),'captions for Arabic audio');
  assert.equal(ctx.subtitleDescription({language:'ar',sourceLanguage:'en',translated:true}),'translated from English');
  state.inspected={...info,site:'Youtube'};element('#subtitleTrackSelect').value='1';ctx.updateSubtitleFormat();
  assert.match(element('#subtitleTrackHelp').textContent,/about a minute.*countdown/);

  // Run the popup's actual handlers to verify the same behavior across the native bridge.
  elementMap.clear();let messages=[];
  const chrome={runtime:{sendMessage:async request=>{messages.push(request);return request.action==='status'?{ok:true,version:'test',drive:{},settings:{destination:'local',outputFormat:'mp4'}}:
    request.action==='inspect'?{ok:true,info:structuredClone(info)}:request.action==='jobs'?{ok:true,downloads:[]}:{ok:true,job:{id:'test'}};}},
    storage:{local:{get:async()=>({})}},tabs:{query:async()=>[{id:1,url:'https://example.test/video'}]},scripting:{executeScript:async()=>[{result:[]}]}};
  const popup=vm.createContext({chrome,Intl,navigator:{language:'en'},$:element,cleanUrl:url=>url||null,discoverMedia(){},
    ACTIVE:new Set(['queued','running']),Option:function(text,value){this.textContent=text;this.value=value;},setInterval(){},document:{getElementById:element,createElement:()=>new Element()}});
  const code=fs.readFileSync('browser-extension/popup.js','utf8').replace(/^import[^\n]*\n/,'').replace('init(); setInterval(refresh, 3000);','');
  vm.runInContext(code,popup);await popup.init();await element('inspect').listeners.click();
  assert.equal(element('subtitleMode').value,'embed');element('burnSize').value='source';
  assert.equal(element('subtitleField').hidden,false);assert.equal(element('subtitleTrack').value,'');
  element('subtitleTrack').value='1';element('audioTrack').value='es';
  await element('downloadForm').listeners.submit({preventDefault(){}});
  assert.equal(messages.findLast(x=>x.action==='download').subtitleLanguage,'fr');
  assert.equal(messages.findLast(x=>x.action==='download').audioFormatId,'es');
  assert.equal(messages.findLast(x=>x.action==='download').subtitleMode,'embed');assert.equal(messages.findLast(x=>x.action==='download').burnSize,'source');
  assert.equal(messages.findLast(x=>x.action==='download').burnAcknowledged,false);
  element('subtitleMode').value='burn';popup.update();await element('downloadForm').listeners.submit({preventDefault(){}});
  assert.equal(messages.findLast(x=>x.action==='download').subtitleMode,'burn','Popup burning must be explicit');
  assert.equal(messages.findLast(x=>x.action==='download').burnAcknowledged,true);
  element('format').value='mp3';popup.update();await element('downloadForm').listeners.submit({preventDefault(){}});
  assert.equal(messages.findLast(x=>x.action==='download').subtitleLanguage,null);
  assert.equal(messages.findLast(x=>x.action==='download').burnAcknowledged,false,'Audio-only selection cannot opt into burning');
  element('url').value='https://example.test/new';element('url').listeners.input();popup.update();
  await element('downloadForm').listeners.submit({preventDefault(){}});
  assert.equal(messages.findLast(x=>x.action==='download').audioFormatId,null);
  assert.equal(element('subtitleMode').value,'embed','Changing popup source clears an earlier burn choice');
  assert.equal(popup.subtitleDescription({language:'ar-orig',sourceLanguage:'ar',originalCaption:true}),'captions for Arabic audio');
  assert.equal(popup.subtitleDescription({language:'ar',sourceLanguage:'en',translated:true}),'translated from English');

  state.jobs=new Map([['active',{id:'active',kind:'download',status:'running',progress:86,message:'Saving MP4',canCancel:true}]]);
  ctx.jobResultMarkup=()=>'';
  vm.runInContext(app.slice(app.indexOf('function downloadStageProgress('),app.indexOf('async function revealResult(')),ctx);
  ctx.updateJobs();assert.match(element('#jobsList').innerHTML,/Cancel download/);
  state.jobs.get('active').cancelRequested=true;state.jobs.get('active').canCancel=false;
  ctx.updateJobs();assert.match(element('#jobsList').innerHTML,/disabled>Cancelling/);
  state.jobs.get('active').status='cancelled';ctx.updateJobs();assert.doesNotMatch(element('#jobsList').innerHTML,/data-cancel-job/);
  const burnJob={kind:'download',status:'running',progress:90.07,message:'Burning subtitles into video · source size · 62%'};
  const stage=ctx.downloadStageProgress(burnJob);
  assert.equal(stage.value,62);assert.equal(stage.label,'Video encoding: 62%');assert.doesNotMatch(stage.message,/62%$/);
  state.jobs=new Map([['burn',{id:'burn',...burnJob,canCancel:true}]]);ctx.updateJobs();
  assert.match(element('#jobsList').innerHTML,/width:62%/);assert.match(element('#jobsList').innerHTML,/Video encoding: 62%/);
  assert.doesNotMatch(element('#jobsList').innerHTML,/>90%/,'Weighted progress must not imply encoding is nearly done');
  assert.equal(ctx.downloadStageProgress({...burnJob,kind:'render'}).value,90.07,'Render progress is unchanged');
  assert.equal(ctx.downloadStageProgress({...burnJob,kind:'download',status:'completed',progress:100,message:'Complete'}).value,100);
  const popupStage=popup.downloadStageProgress(burnJob);assert.equal(popupStage.value,62);assert.equal(popupStage.label,'Video encoding: 62%');
  const muxJob={...burnJob,message:'Saving video and audio without re-encoding · 12%'};
  assert.equal(popup.downloadStageProgress(muxJob).value,12);assert.equal(popup.downloadStageProgress(muxJob).label,'Saving file: 12%');
  assert.equal(ctx.downloadStageProgress(muxJob).label,'Saving file: 12%','Stream copying must not be called video encoding');
  popup.renderJobs([{...burnJob,id:'phase',status:'running'}]);
  let article=element('jobs').children[0];assert.match(article.children[1].textContent,/Video encoding: 62%/);assert.equal(article.children[2].value,62);
  popup.renderJobs([{id:'done',status:'completed',progress:100,message:'Complete',qualityPreserved:true,containerFallback:'Saved as MKV to keep the source quality.'}]);
  article=element('jobs').children[0];assert.match(article.children[1].textContent,/Original video and selected audio preserved/);assert.match(article.children[1].textContent,/Saved as MKV/);
  console.log('App and popup subtitle selection, None, audio-only formats, and stale-source resets passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
