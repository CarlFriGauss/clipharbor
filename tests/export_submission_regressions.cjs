const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const destinations = fs.readFileSync('static/destinations.js', 'utf8');
const app = fs.readFileSync('static/app.js', 'utf8');
const retryCode = destinations.slice(destinations.indexOf('function deliveryMarkup('), destinations.indexOf('const googleSignIns'));
const exportCode = app.slice(app.indexOf('async function startExport()'), app.indexOf('function applyInspectorChange'));

(async () => {
  let resolveRequest, calls = 0, body;
  const original = {id:'parent',status:'failed',result:{path:'test.mp4',token:'file'},deliveryRequest:{destination:'facebook_browser',deliveryOptions:{audience:'only_me'}}};
  const context = vm.createContext({state:{jobs:new Map([['parent',original]])},retrySubmissions:new Set(),escapeHtml:value=>value,destinationNames:{},updateJobs(){},trackJob(){},toast(){},api:async (url,options)=>{calls++;body=JSON.parse(options.body);return new Promise(resolve=>{resolveRequest=resolve;});}});
  vm.runInContext(retryCode,context);
  assert.match(context.deliveryMarkup(original),/Retry upload/);
  const first = context.retryDelivery('parent');
  assert.match(context.deliveryMarkup(original),/disabled/);
  const second = context.retryDelivery('parent');
  assert.equal(calls,1);
  assert.equal(body.retryOf,'parent');
  resolveRequest({id:'child'});
  await Promise.all([first,second]);
  await context.retryDelivery('parent');
  assert.equal(calls,1,'A successful retry must remove the old action');
  assert.equal(original.retryJobId,'child');
  assert.doesNotMatch(context.deliveryMarkup(original),/Retry upload/);

  let exportResolve, exports = 0, requestBody;
  const button = {};
  const exporting = vm.createContext({exportSubmitting:false,exportSource:{token:'file'},exportRequestId:'f'.repeat(32),deliveryPayload:()=>({destination:'facebook_browser',deliveryOptions:{audience:'only_me'}}),$:selector=>selector==='#startExport'?button:{close(){}},trackJob(){},setView(){},toast(){},updateDestination(){},api:async(url,options)=>{exports++;requestBody=JSON.parse(options.body);return new Promise(resolve=>{exportResolve=resolve;});}});
  vm.runInContext(exportCode,exporting);
  const post=exporting.startExport();
  await exporting.startExport();
  assert.equal(exports,1,'Two clicks during one submission must start one request');
  assert.equal(button.disabled,true);
  assert.equal(requestBody.requestId,'f'.repeat(32));
  exportResolve({id:'export'});await post;
  assert.equal(exporting.exportSubmitting,false);
  console.log('Export double-click and repeated Retry submission regressions passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
