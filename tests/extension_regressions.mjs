import assert from "node:assert/strict";
import {cleanUrl, contextUrl} from "../browser-extension/shared.js";

for (const invalid of ["javascript:alert(1)", "file:///secret.mp4", "https://user:password@example.com", "https://example.com/\nvideo", "blob:https://example.com/x"]) assert.equal(cleanUrl(invalid), null);
assert.equal(contextUrl({pageUrl: "https://www.youtube.com/watch?v=123", srcUrl: "https://stream.example.com/video-only.mp4"}), "https://www.youtube.com/watch?v=123");
assert.equal(contextUrl({pageUrl: "https://example.com/article", srcUrl: "https://cdn.example.com/movie.mp4"}), "https://cdn.example.com/movie.mp4");
assert.equal(contextUrl({pageUrl: "https://example.com/feed", linkUrl: "https://x.com/user/status/123"}), "https://x.com/user/status/123");

let listener;
const state = {};
let nextId = 0;
const nativeRequests=[];
globalThis.chrome = {
  runtime: {id: "extension", sendNativeMessage: async (host, message) => {
    assert.equal(host, "com.clipharbor.downloader");
    nativeRequests.push(message);
    if(message.action === "inspect") return {ok:true,info:{title:"Source",subtitleTracks:[{language:"fr",source:"automatic"}]}};
    if (message.action === "download") return {ok: true, job: {id: String(++nextId).padStart(32, "0"), status: "queued", progress: 0}};
    if (message.action === "job") return {ok: true, job: {id: message.jobId, status: "completed", progress: 100, name: "download.mp4"}};
    return {ok: true};
  }, onInstalled: {addListener() {}}, onStartup: {addListener() {}}, onMessage: {addListener(fn) {listener = fn;}}},
  action: {setBadgeText: async () => {}, setBadgeBackgroundColor: async () => {}, setTitle: async () => {}},
  alarms: {create: async () => {}, clear: async () => {}, onAlarm: {addListener() {}}},
  contextMenus: {onClicked: {addListener() {}}, removeAll() {}, create() {}},
  storage: {local: {get: async keys => Object.fromEntries((Array.isArray(keys) ? keys : [keys]).map(key => [key, structuredClone(state[key])])),
    set: async values => Object.assign(state, structuredClone(values))}},
};
await import("../browser-extension/background.js");
assert.equal(listener({action: "download"}, {id: "foreign"}, () => assert.fail("Foreign sender accepted")), false);
assert.equal(listener({action: "download"}, {id: "extension", tab: {id: 2}}, () => assert.fail("Page sender accepted")), false);
function send(message) { return new Promise(resolve => assert.equal(listener(message, {id: "extension"}, resolve), true)); }
const one = send({action: "download", url: "https://example.com/one.mp4", destination: "local", outputFormat: "mp4"});
const two = send({action: "download", url: "https://example.com/two.mp4", destination: "drive", outputFormat: "mp4"});
const poll = send({action: "jobs"});
for (const response of await Promise.all([one, two, poll])) assert.equal(response.ok, true);
assert.equal(state.downloads.length, 2, "Concurrent popup/right-click/poll updates must retain both accepted jobs");
assert.ok(state.downloads.every(job => job.status === "completed"));
assert.equal(nextId, 2, "Polling must not resubmit downloads");
assert.equal((await send({action: "unknown"})).ok, false);
assert.equal((await send({action:"inspect",url:"https://example.com/video"})).info.subtitleTracks[0].language,"fr");
await send({action:"download",url:"https://example.com/video",destination:"local",outputFormat:"mp4",audioFormatId:"audio-es",subtitleLanguage:"fr",subtitleSource:"automatic"});
const trackRequest=nativeRequests.findLast(item=>item.action==="download");
assert.equal(trackRequest.audioFormatId,"audio-es");assert.equal(trackRequest.subtitleLanguage,"fr");assert.equal(trackRequest.subtitleSource,"automatic");
console.log("Extension URL, sender isolation, concurrent download tracking, and no-retry regressions passed.");
