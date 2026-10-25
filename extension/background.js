// Stage browser extension.
//
// Keeps a live link (WebSocket) to the Stage app on this PC while both are running:
//  - sends every open tab whenever tabs change, and whenever Stage asks ("park")
//  - opens a park's tabs as a named tab group when Stage resumes it
// The link also keeps this extension awake, so Stage never waits on a sleeping one.
//
// If the browser was closed, Stage opens 127.0.0.1:47321/restore/<token> instead;
// we spot that tab, fetch the tabs over plain HTTP, and open the group.
//
// Everything stays on this computer: the only address we talk to is 127.0.0.1.

const STAGE = "http://127.0.0.1:47321";
const LIVE = "ws://127.0.0.1:47322";
const BROWSER = (navigator.userAgentData?.brands || []).some(b => b.brand === "Microsoft Edge") ? "edge" : "chrome";
const COLORS = ["blue", "red", "yellow", "green", "pink", "purple", "cyan", "orange"];

// ---- the live link ------------------------------------------------------------------
let socket = null;
let keepAwake = null;

function connect() {
  if (socket && socket.readyState <= WebSocket.OPEN) return;  // connecting or connected
  try {
    socket = new WebSocket(LIVE);
  } catch (e) {
    socket = null;
    return;
  }
  socket.onopen = () => {
    send({ type: "hello", browser: BROWSER });
    report();
    // Chrome puts idle extensions to sleep after 30 s; a message every 20 s keeps us awake
    keepAwake = setInterval(() => send({ type: "ping" }), 20000);
  };
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.type === "report") report();
    if (message.type === "restore") openGroup(message);
  };
  socket.onclose = () => {
    clearInterval(keepAwake);
    socket = null;
  };
  socket.onerror = () => {};  // Stage not running: onclose follows, we retry on the next alarm
}

function send(message) {
  if (socket?.readyState !== WebSocket.OPEN) return false;
  socket.send(JSON.stringify(message));
  return true;
}

// A line in Stage's log (data/stage.log), so problems here can be seen there
function debug(text) {
  if (!send({ type: "log", text: String(text) })) {
    fetch(`${STAGE}/debug`, { method: "POST", body: String(text) }).catch(() => {});
  }
}

// ---- report open tabs ----------------------------------------------------------------
let pending = null;
function reportSoon() {
  // Many tab events fire at once (e.g. opening a window): send one report after they settle
  clearTimeout(pending);
  pending = setTimeout(report, 300);
}

// Where a YouTube video is, in whole seconds (null if not a video, or the tab is asleep)
const YOUTUBE_VIDEO = /^https:\/\/(www\.|m\.)?youtube\.com\/watch/;
async function videoTime(tab) {
  if (!YOUTUBE_VIDEO.test(tab.url || "")) return null;
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => { const v = document.querySelector("video"); return v ? Math.floor(v.currentTime) : null; },
    });
    return result?.result ?? null;
  } catch (e) {
    return null;
  }
}

async function report() {
  scanForRestores();
  const windows = await chrome.windows.getAll({ populate: true, windowTypes: ["normal"] });
  const groups = Object.fromEntries((await chrome.tabGroups.query({})).map(g => [g.id, g.title || ""]));
  const describe = async t => ({ title: t.title, url: t.url, active: t.active, pinned: t.pinned,
                                 group: t.groupId >= 0 ? groups[t.groupId] : "", time: await videoTime(t) });
  const body = {
    type: "report",
    browser: BROWSER,
    windows: await Promise.all(windows.map(async w => ({
      id: w.id,
      focused: w.focused,
      tabs: await Promise.all(w.tabs.filter(t => t.url && !t.url.startsWith(STAGE)).map(describe)),
    }))),
  };
  if (send(body)) return;
  connect();  // not linked yet: try, and send this one over plain HTTP meanwhile
  try {
    await fetch(`${STAGE}/tabs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch (e) {
    // Stage isn't running: nothing to do
  }
}

for (const event of [chrome.tabs.onCreated, chrome.tabs.onRemoved, chrome.tabs.onActivated, chrome.tabs.onMoved,
                     chrome.tabs.onAttached, chrome.tabs.onDetached, chrome.windows.onCreated,
                     chrome.windows.onRemoved, chrome.windows.onFocusChanged, chrome.tabGroups.onUpdated]) {
  event.addListener(reportSoon);
}
chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
  if ((change.url || change.status === "complete") && tab.url?.startsWith(`${STAGE}/restore/`)) return restoreFromTab(tab);
  if (change.url || change.title || change.pinned !== undefined || change.groupId !== undefined) reportSoon();
});

// Every 30 s: reconnect if Stage started after the browser (this also wakes us up)
chrome.alarms.create("link", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => { connect(); });
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);

// ---- open a park's tabs as a tab group ----------------------------------------------
async function openGroup(park, windowId) {
  if (windowId === undefined) {
    const last = await chrome.windows.getLastFocused({ windowTypes: ["normal"] }).catch(() => null);
    windowId = last ? last.id : (await chrome.windows.create({ focused: true })).id;
  }
  debug(`restoring ${park.urls.length} tab(s) as "${park.name}"`);
  const tabIds = [];
  for (const url of park.urls) {
    tabIds.push((await chrome.tabs.create({ windowId, url, active: false })).id);
  }
  if (!tabIds.length) return;
  const groupId = await chrome.tabs.group({ tabIds, createProperties: { windowId } });
  await chrome.tabGroups.update(groupId, { title: park.name, color: COLORS[park.color % COLORS.length] });
  await chrome.tabs.update(tabIds[0], { active: true });
  await chrome.windows.update(windowId, { focused: true });
}

// Browser was closed: Stage opened its restore page. Fetch the tabs and replace that page.
const handled = new Set();
async function restoreFromTab(triggerTab) {
  if (handled.has(triggerTab.id)) return;
  handled.add(triggerTab.id);
  const token = (triggerTab.url || triggerTab.pendingUrl).split("/restore/")[1].split(/[?#]/)[0];
  let park;
  try {
    const response = await fetch(`${STAGE}/restore/${token}.json`);
    if (!response.ok) return debug(`restore ${token}: Stage answered ${response.status}`);
    park = await response.json();
  } catch (e) {
    return debug(`restore ${token}: ${e}`);  // leave Stage's page open, it lists the links
  }
  await openGroup(park, triggerTab.windowId);
  await chrome.tabs.remove(triggerTab.id);
}

// The restore page can load before we wake up and its event is then missed: look for it
async function scanForRestores() {
  for (const tab of await chrome.tabs.query({})) {
    if ((tab.url || tab.pendingUrl || "").startsWith(`${STAGE}/restore/`)) restoreFromTab(tab);
  }
}

connect();
scanForRestores();
