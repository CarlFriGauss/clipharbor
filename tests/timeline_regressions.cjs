const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const nodes = new Map();
const node = selector => {
  if (!nodes.has(selector)) nodes.set(selector, {style:{}, value:'', textContent:'', currentTime:3990,
    classList:{contains:()=>true,toggle(){},add(){},remove(){}},pause(){},load(){},removeAttribute(){},
    addEventListener(){},clientWidth:1200,scrollLeft:0});
  return nodes.get(selector);
};
const context = vm.createContext({console, crypto:webcrypto, document:{querySelector:node,querySelectorAll:()=>[],activeElement:null},
  window:{}, setTimeout:()=>0,clearTimeout(){},cancelAnimationFrame(){},localStorage:{setItem(){}}});
vm.runInContext(fs.readFileSync('static/app.js','utf8').replace(/init\(\);\s*$/, ''),context);
vm.runInContext(`renderEditor=()=>{};previewAsset=()=>{};toast=()=>{};renderProjectHeader=()=>{};updateHistoryButtons=()=>{};`,context);
function run(code) {return vm.runInContext(code,context);}
run(`state.clips=[{id:'a',assetId:'src',kind:'audio',layer:0,start:0,in:0,out:10983.84,speed:1}];setClipSelection(['a']);state.playhead=4013.731;state.previewClipId='a';`);
run('cutAtPlayerPosition()');
assert.equal(run('state.clips[0].out'),4013.731,'cut must ignore stale player currentTime');
assert.equal(run('state.clips[1].start'),4013.731);
assert.equal(run('state.playhead'),4013.731);
run(`state.clips=[{id:'v',assetId:'src',kind:'video',layer:0,start:2,in:10,out:30,speed:2},{id:'a',assetId:'src',kind:'audio',layer:0,start:0,in:0,out:20,speed:1}];state.selectedLayerKeys=new Set(['video:0','audio:0']);state.playhead=5.123;`);
run('cutAtPlayerPosition()');
assert.ok(Math.abs(run('state.clips[0].out')-16.246)<1e-10);
assert.equal(run('state.clips[1].out'),5.123);
assert.equal(run('formatTime(3599.999,true)'), '01:00:00.00');
assert.equal(run(`parsePosition('01:06:28.123')`),3988.123);
assert.equal(run(`clipsAreSourceContinuous({assetId:'a',kind:'audio',layer:0,start:0,in:0,out:1,speed:1},{assetId:'a',kind:'audio',layer:0,start:1,in:1.02,out:2,speed:1})`),false,'a deliberate 20ms source cut must not be bridged');
console.log('Exact cursor cuts, selected-layer cuts, speed mapping, and time formatting passed.');
run(`state.assets=[{id:'source-a',media:{name:'A.mp4'}},{id:'source-b',media:{name:'B.mp4'}}];state.selectedAssetId='source-a';state.clips=[{id:'b-section',assetId:'source-b',kind:'video',layer:0,start:0,in:0,out:3,speed:1}];clearSelection();`);
assert.equal(run('inspectorContext().kind'),'source');
assert.equal(run('inspectorContext().asset.media.name'),'A.mp4');
run(`setClipSelection(['b-section'],'b-section');`);
assert.equal(run('inspectorContext().kind'),'sections');
assert.equal(run('inspectorContext().asset.media.name'),'B.mp4','timeline selection must override the previously auditioned source');
run(`clearSelection();state.selectedLayerKeys=new Set(['audio:2']);`);
assert.equal(run('inspectorContext().kind'),'layers','even an empty layer must show its own properties');
assert.equal(run('inspectorContext().layers[0]'),'audio:2');
assert.equal(run('inspectorContext().asset'),null,'an empty layer must not show unrelated source properties');
run(`state.selectedLayerKeys=new Set(['video:0']);state.selectedClipIds=new Set(['b-section']);state.primaryClipId='b-section';`);
assert.equal(run('inspectorContext().clips.length'),1);
assert.equal(run('inspectorContext().asset.media.name'),'B.mp4');
vm.runInContext(fs.readFileSync('static/editor-layout.js','utf8'),context);
for(const width of [568,720,1024,1920])for(const media of [140,220,420])for(const properties of [180,260,420])for(const open of [true,false]){
  const fitted=run(`editorPanelWidths(${width},${media},${properties},${open})`);
  const center=width-44-(open?20:10)-fitted.media-fitted.properties;
  assert.ok(center>=159,'resized panels must leave room for the video');
  assert.ok(fitted.properties>=180&&fitted.properties<=420);
  assert.ok(open?fitted.media>=140&&fitted.media<=420:fitted.media===0);
}
console.log('Source, section, and empty-layer properties; preview space with open and collapsed Media passed.');
