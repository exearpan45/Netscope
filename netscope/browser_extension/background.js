// NETSCOPE Tab Telemetry Bridge
// Measures HTTP Content-Length & request body sizes per tab via webRequest.
// Explicitly labeled as browser-reported estimates (excludes TLS framing & QUIC overhead).

const HOST_NAME = "com.netscope.monitor";
const LOCAL_ENDPOINT = "http://127.0.0.1:3000/api/browser/telemetry";
const tabBuffers = new Map();

function detectBrowserName() {
  const ua = navigator.userAgent;
  if (ua.includes("Brave")) return "Brave";
  if (ua.includes("Edg/")) return "Microsoft Edge";
  if (ua.includes("Firefox/")) return "Firefox";
  if (ua.includes("Chromium/")) return "Chromium";
  if (ua.includes("Chrome/")) return "Google Chrome";
  return "Browser";
}

function getDomain(url) {
  try {
    return new URL(url).hostname || "internal";
  } catch {
    return "internal";
  }
}

function ensureTab(tabId, url, title, active) {
  if (tabId < 0) return null;
  if (!tabBuffers.has(tabId)) {
    tabBuffers.set(tabId, {
      tab_id: String(tabId),
      browser_name: detectBrowserName(),
      tab_title: title || getDomain(url),
      domain: getDomain(url),
      is_active: Boolean(active),
      rx_delta_bytes: 0,
      tx_delta_bytes: 0,
    });
  }
  const entry = tabBuffers.get(tabId);
  if (url) entry.domain = getDomain(url);
  if (title) entry.tab_title = title;
  if (typeof active === "boolean") entry.is_active = active;
  return entry;
}

chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    if (details.tabId < 0) return;
    let txBytes = 0;
    if (details.requestBody) {
      if (details.requestBody.raw) {
        for (const part of details.requestBody.raw) {
          if (part.bytes) txBytes += part.bytes.byteLength;
        }
      } else if (details.requestBody.formData) {
        txBytes += JSON.stringify(details.requestBody.formData).length;
      }
    }
    const entry = ensureTab(details.tabId, details.url);
    if (entry) entry.tx_delta_bytes += txBytes;
  },
  { urls: ["<all_urls>"] },
  ["requestBody"]
);

chrome.webRequest.onCompleted.addListener(
  (details) => {
    if (details.tabId < 0) return;
    let rxBytes = 0;
    if (details.responseHeaders) {
      for (const h of details.responseHeaders) {
        if (h.name.toLowerCase() === "content-length" && h.value) {
          const parsed = parseInt(h.value, 10);
          if (!Number.isNaN(parsed) && parsed > 0) rxBytes += parsed;
        }
      }
    }
    const entry = ensureTab(details.tabId, details.url);
    if (entry) entry.rx_delta_bytes += rxBytes;
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"]
);

async function flushTelemetry() {
  if (tabBuffers.size === 0) return;
  try {
    const tabs = await chrome.tabs.query({});
    for (const t of tabs) {
      if (t.id >= 0 && tabBuffers.has(t.id)) {
        ensureTab(t.id, t.url, t.title, t.active);
      }
    }
  } catch {
    // ignore tab query errors
  }

  const payloadTabs = [];
  for (const [id, entry] of tabBuffers.entries()) {
    if (entry.rx_delta_bytes > 0 || entry.tx_delta_bytes > 0 || entry.is_active) {
      payloadTabs.push({
        ...entry,
        rx_rate_bps: entry.rx_delta_bytes / 2,
        tx_rate_bps: entry.tx_delta_bytes / 2,
      });
      entry.rx_delta_bytes = 0;
      entry.tx_delta_bytes = 0;
    } else {
      tabBuffers.delete(id);
    }
  }

  if (payloadTabs.length === 0) return;

  // Prefer Native Messaging when installed, fallback to local loopback API
  try {
    chrome.runtime.sendNativeMessage(HOST_NAME, { tabs: payloadTabs }, () => {
      if (chrome.runtime.lastError) {
        fetch(LOCAL_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tabs: payloadTabs }),
        }).catch(() => {});
      }
    });
  } catch {
    fetch(LOCAL_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tabs: payloadTabs }),
    }).catch(() => {});
  }
}

setInterval(flushTelemetry, 2000);
