const MCP_SERVER = "http://localhost:8766";
const CONCIERGE_URL = "https://concierge.sanofi.com/";

const dotServer = document.getElementById("dotServer");
const dotLogin = document.getElementById("dotLogin");
const dotSync = document.getElementById("dotSync");
const txtServer = document.getElementById("txtServer");
const txtLogin = document.getElementById("txtLogin");
const txtSync = document.getElementById("txtSync");
const syncBtn = document.getElementById("syncBtn");
const resultEl = document.getElementById("result");
const resultTitle = document.getElementById("resultTitle");
const resultDetail = document.getElementById("resultDetail");
const footer = document.getElementById("footer");

function setIndicator(dot, txt, type, label) {
  dot.className = `dot ${type}`;
  txt.textContent = label;
}

async function checkMcpServer() {
  try {
    const resp = await fetch(`${MCP_SERVER}/auth/status`, {
      signal: AbortSignal.timeout(3000),
    });
    if (!resp.ok) return { online: true, synced: false };
    const data = await resp.json();
    return { online: true, synced: data.connected };
  } catch {
    return { online: false, synced: false };
  }
}

function getConciergeToken() {
  return new Promise((resolve) => {
    chrome.cookies.getAll({ url: CONCIERGE_URL }, (cookies) => {
      if (chrome.runtime.lastError) {
        resolve(null);
        return;
      }
      const token = cookies.find((c) => c.name === "access_token");
      resolve(token ? token.value : null);
    });
  });
}

async function syncToMcp(accessToken) {
  const resp = await fetch(`${MCP_SERVER}/auth/cookies`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_token: accessToken }),
  });
  if (!resp.ok) throw new Error(`Server returned ${resp.status}`);
  const data = await resp.json();
  if (!data.ok) throw new Error("Sync rejected by server");
  return data;
}

function showResult(type, title, detail) {
  resultEl.className = `result show ${type}`;
  resultTitle.textContent = title;
  resultDetail.textContent = detail;
}

function hideResult() {
  resultEl.className = "result";
}

async function init() {
  const [mcp, token] = await Promise.all([checkMcpServer(), getConciergeToken()]);

  if (mcp.online) {
    setIndicator(dotServer, txtServer, "ok", "Online");
  } else {
    setIndicator(dotServer, txtServer, "error", "Offline");
    setIndicator(dotLogin, txtLogin, "warn", "—");
    setIndicator(dotSync, txtSync, "warn", "—");
    showResult("fail", "MCP Server Unreachable", "Run: docker compose up -d in concierge/");
    syncBtn.disabled = true;
    return;
  }

  if (token) {
    setIndicator(dotLogin, txtLogin, "ok", "Active");
  } else {
    setIndicator(dotLogin, txtLogin, "error", "Not logged in");
    setIndicator(dotSync, txtSync, "warn", "—");
    showResult(
      "fail",
      "Concierge Login Required",
      "Open concierge.sanofi.com and sign in with SSO first."
    );
    syncBtn.disabled = true;
    return;
  }

  if (mcp.synced) {
    setIndicator(dotSync, txtSync, "ok", "Synced");
    syncBtn.textContent = "Re-sync Session";
    footer.textContent = "Concierge tools are ready in Cursor.";
  } else {
    setIndicator(dotSync, txtSync, "warn", "Not synced");
    syncBtn.textContent = "Sync Session";
  }

  syncBtn.disabled = false;
}

syncBtn.addEventListener("click", async () => {
  syncBtn.disabled = true;
  syncBtn.textContent = "Syncing…";
  hideResult();
  setIndicator(dotSync, txtSync, "checking", "Syncing…");

  try {
    const token = await getConciergeToken();
    if (!token) {
      setIndicator(dotLogin, txtLogin, "error", "Not logged in");
      setIndicator(dotSync, txtSync, "error", "Failed");
      showResult(
        "fail",
        "Session Expired",
        "Open concierge.sanofi.com and sign in again."
      );
      syncBtn.textContent = "Sync Session";
      syncBtn.disabled = false;
      return;
    }

    await syncToMcp(token);

    setIndicator(dotSync, txtSync, "ok", "Synced");
    showResult(
      "success",
      "Session Synced!",
      "Switch to Cursor — Concierge tools are ready."
    );
    syncBtn.textContent = "Re-sync Session";
    syncBtn.disabled = false;
    footer.textContent = "Concierge tools are ready in Cursor.";
  } catch (e) {
    setIndicator(dotSync, txtSync, "error", "Failed");
    showResult("fail", "Sync Failed", e.message);
    syncBtn.textContent = "Sync Session";
    syncBtn.disabled = false;
  }
});

init();
