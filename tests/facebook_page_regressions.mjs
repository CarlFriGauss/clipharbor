import assert from "node:assert/strict";
import {facebookPage} from "../facebook-extension/page.js";

// A minimal DOM fixture focuses on the safety boundary: existing captions,
// attachments, wrong origins and login forms must stop before any click.
let clicks=0;
const box={innerText:"An existing draft",value:"",getAttribute:()=>null,getClientRects:()=>[{}]};
const composer={getAttribute:()=>"Create post",innerText:"Create post",textContent:"Create post",getClientRects:()=>[{}],querySelectorAll:selector=>selector.includes('contenteditable')?[box]:[]};
globalThis.location={origin:"https://www.facebook.com",pathname:"/Example.Person"};
globalThis.getComputedStyle=()=>({visibility:"visible"});
globalThis.document={querySelector:()=>null,querySelectorAll:selector=>selector==='[role=dialog]'?[composer]:[],getElementById:()=>null};
assert.match(facebookPage("prepare",{caption:"New export caption"}).error,/draft/i);
assert.equal(clicks,0);
box.innerText="";
composer.querySelectorAll=selector=>selector.includes('contenteditable')?[box]:selector==='button,[role=button]'?[{getAttribute:name=>name==="aria-label"?"Remove Post Attachment":null,getClientRects:()=>[{}],click:()=>clicks++}]:[];
assert.match(facebookPage("prepare",{caption:""}).error,/media draft/i);
assert.equal(clicks,0);
globalThis.location.origin="https://evil.example";
assert.match(facebookPage("publish",{audience:"only_me"}).error,/left Facebook/);
globalThis.location.origin="https://www.facebook.com";
globalThis.location.pathname="/checkpoint/";
assert.match(facebookPage("open").error,/security check/);
assert.equal(clicks,0);
console.log("Facebook draft/attachment preservation and origin/login stop checks passed.");

globalThis.location.pathname="/Example.Person";
let oldNotice=false;
const notice={getAttribute:name=>name==="data-clipharbor-before-post"?(oldNotice?"task-marker":null):null,innerText:"Your post has successfully been shared with SELF",getClientRects:()=>[{}]};
document.querySelectorAll=selector=>selector==='[role=alert],[role=status]'?[notice]:[];
assert.equal(facebookPage("confirm",{marker:"task-marker",profileUrl:"https://www.facebook.com/Example.Person"}).confirmed,true);
oldNotice=true;
assert.equal(facebookPage("confirm",{marker:"task-marker"}).confirmed,undefined,"An old success notice cannot confirm a new post");
oldNotice=false;
notice.innerText="Your video is processing";
assert.equal(facebookPage("confirm",{marker:"task-marker"}).confirmed,undefined);
console.log("Facebook confirmation requires a fresh success notice.");
