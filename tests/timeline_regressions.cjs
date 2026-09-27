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
