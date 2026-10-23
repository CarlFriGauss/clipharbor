export const HOST = "com.clipharbor.downloader";
export const ACTIVE = new Set(["queued", "running"]);

export function cleanUrl(value) {
  if (typeof value !== "string" || value.length > 16384 || /[\u0000-\u001f]/u.test(value)) return null;
  try {
    const url = new URL(value.trim());
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? value.trim() : null;
  } catch { return null; }
}

export function contextUrl(info) {
  if (info.linkUrl) return cleanUrl(info.linkUrl);
  const page = cleanUrl(info.frameUrl) || cleanUrl(info.pageUrl);
  // Social players often expose a transient or video-only stream. Send their
  // permalink to the existing extractor so it can find the matching audio.
  const social = page && /(^|\.)(youtube\.com|youtu\.be|facebook\.com|fb\.watch|instagram\.com|x\.com|twitter\.com|tiktok\.com)$/i.test(new URL(page).hostname);
  return (social ? page : cleanUrl(info.srcUrl)) || page;
}

// Serialized by chrome.scripting only after the user clicks the extension.
// Read visible media and nearby permalinks; never inspect cookies or form data.
export function discoverMedia() {
  const results = [];
  const media = [...document.querySelectorAll("video,audio")].slice(0, 30);
  for (const [index, element] of media.entries()) {
    const rect = element.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) continue;
    const article = element.closest("article,[role=article]");
    const links = article ? [...article.querySelectorAll("a[href]")] : [];
    const permalink = links.find(link => /\/(status|reel|reels|videos|watch|p)\//.test(link.pathname) && !/\/(photo|analytics|likes|retweets)/.test(link.pathname));
    const source = element.currentSrc || element.src;
    const direct = /^https?:\/\//i.test(source) && /\.(mp4|webm|mov|m4v|mkv|mp3|m4a|wav)(\?|$)/i.test(source) ? source : null;
    const social = /(^|\.)(youtube\.com|youtu\.be|facebook\.com|instagram\.com|x\.com|twitter\.com|tiktok\.com)$/i.test(location.hostname);
    const url = permalink?.href || (!social && direct) || location.href;
    const onScreen = rect.bottom > 0 && rect.top < innerHeight && rect.right > 0 && rect.left < innerWidth;
    results.push({url, label: `${element.tagName === "AUDIO" ? "Audio" : "Video"} ${index + 1}${!element.paused ? " · playing" : onScreen ? " · on screen" : ""}`, score: !element.paused ? 2 : onScreen ? 1 : 0});
  }
  return results.sort((a, b) => b.score - a.score);
}
