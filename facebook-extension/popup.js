const $ = id => document.getElementById(id);
async function request(action) {
  const response = await chrome.runtime.sendMessage({action});
  if (!response?.ok) throw new Error(response?.error || "ClipHarbor is unavailable.");
  return response;
}
function show(status) {
  $("status").textContent = status.enabled ? "Connected: " + status.name : "Browser posting is stopped. Open your own Facebook profile to connect.";
  $("disable").hidden = !status.enabled;
  if(status.message) $("message").textContent = status.message;
}
$("connect").addEventListener("click",async()=>{
  $("connect").disabled = true;
  try { show(await request("connect")); }
  catch(error) { $("message").textContent = error.message; }
  finally { $("connect").disabled = false; }
});
$("disable").addEventListener("click",async()=>{
  try { show(await request("disable")); } catch(error) { $("message").textContent=error.message; }
});
request("status").then(show).catch(error=>$("status").textContent=error.message);
