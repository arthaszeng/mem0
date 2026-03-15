const AUTH_SERVER = "https://arthaszeng.top/auth";
const MCP_SERVER = "https://arthaszeng.top/concierge-mcp";
const CONCIERGE_URL = "https://concierge.sanofi.com/";

// --- DOM refs ---
const loginCard = document.getElementById("loginCard");
const userBar = document.getElementById("userBar");
const statusCard = document.getElementById("statusCard");
const syncBtn = document.getElementById("syncBtn");
const loginBtn = document.getElementById("loginBtn");
const signoutBtn = document.getElementById("signoutBtn");
const displayName = document.getElementById("displayName");
const usernameInput = document.getElementById("username");
const passwordInput = document.getElementById("password");

const dotServer = document.getElementById("dotServer");
const dotLogin = document.getElementById("dotLogin");
const dotSync = document.getElementById("dotSync");
const txtServer = document.getElementById("txtServer");
const txtLogin = document.getElementById("txtLogin");
const txtSync = document.getElementById("txtSync");
const resultEl = document.getElementById("result");
const resultTitle = document.getElementById("resultTitle");
const resultDetail = document.getElementById("resultDetail");
const footer = document.getElementById("footer");

// --- State ---
let authToken = null;
let authUsername = null;

function setIndicator(dot, txt, type, label) {
  dot.className = `dot ${type}`;
  txt.textContent = label;
}

function showResult(type, title, detail) {
  resultEl.className = `result show ${type}`;
  resultTitle.textContent = title;
  resultDetail.textContent = detail;
}

function hideResult() {
  resultEl.className = "result";
}

function showLoggedIn() {
  loginCard.classList.add("hidden");
  userBar.classList.remove("hidden");
  statusCard.classList.remove("hidden");
  syncBtn.classList.remove("hidden");
  displayName.textContent = authUsername;
}

function showLoggedOut() {
  loginCard.classList.remove("hidden");
  userBar.classList.add("hidden");
  statusCard.classList.add("hidden");
  syncBtn.classList.add("hidden");
  hideResult();
  footer.textContent = "";
}

// --- Auth ---
async function signIn() {
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  if (!username || !password) {
    showResult("fail", "Missing Credentials", "Enter both username and password.");
    return;
  }

  loginBtn.disabled = true;
  loginBtn.textContent = "Signing in…";
  hideResult();

  try {
    const resp = await fetch(`${AUTH_SERVER}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || `Login failed (${resp.status})`);
    }
    const data = await resp.json();
    authToken = data.access_token;
    authUsername = data.user?.username || username;

    await chrome.storage.local.set({ authToken, authUsername });

    showLoggedIn();
    checkStatus();
  } catch (e) {
    showResult("fail", "Sign In Failed", e.message);
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = "Sign In";
  }
}

async function signOut() {
  authToken = null;
  authUsername = null;
  await chrome.storage.local.remove(["authToken", "authUsername"]);
  showLoggedOut();
}

// --- MCP status check ---
async function checkMcpServer() {
  try {
    const resp = await fetch(`${MCP_SERVER}/auth/status`, {
      signal: AbortSignal.timeout(5000),
      headers: { "Authorization": `Bearer ${authToken}` },
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
      if (chrome.runtime.lastError) { resolve(null); return; }
      const token = cookies.find((c) => c.name === "access_token");
      resolve(token ? token.value : null);
    });
  });
}

async function syncToMcp(accessToken) {
  const resp = await fetch(`${MCP_SERVER}/auth/cookies`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${authToken}`,
    },
    body: JSON.stringify({ access_token: accessToken }),
  });
  if (!resp.ok) throw new Error(`Server returned ${resp.status}`);
  const data = await resp.json();
  if (!data.ok) throw new Error("Sync rejected by server");
  return data;
}

// --- Status check flow ---
async function checkStatus() {
  setIndicator(dotServer, txtServer, "checking", "Checking…");
  setIndicator(dotLogin, txtLogin, "checking", "Checking…");
  setIndicator(dotSync, txtSync, "checking", "Checking…");
  hideResult();

  const [mcp, conciergeToken] = await Promise.all([checkMcpServer(), getConciergeToken()]);

  if (mcp.online) {
    setIndicator(dotServer, txtServer, "ok", "Online");
  } else {
    setIndicator(dotServer, txtServer, "error", "Offline");
    setIndicator(dotLogin, txtLogin, "warn", "—");
    setIndicator(dotSync, txtSync, "warn", "—");
    showResult("fail", "MCP Server Unreachable", "Check that the server is running.");
    syncBtn.disabled = true;
    return;
  }

  if (conciergeToken) {
    setIndicator(dotLogin, txtLogin, "ok", "Active");
  } else {
    setIndicator(dotLogin, txtLogin, "error", "Not logged in");
    setIndicator(dotSync, txtSync, "warn", "—");
    showResult("fail", "Concierge Login Required", "Open concierge.sanofi.com and sign in with SSO first.");
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

// --- Sync button ---
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
      showResult("fail", "Session Expired", "Open concierge.sanofi.com and sign in again.");
      syncBtn.textContent = "Sync Session";
      syncBtn.disabled = false;
      return;
    }

    await syncToMcp(token);

    setIndicator(dotSync, txtSync, "ok", "Synced");
    showResult("success", "Session Synced!", "Switch to Cursor — Concierge tools are ready.");
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

// --- Event listeners ---
loginBtn.addEventListener("click", signIn);
signoutBtn.addEventListener("click", signOut);

passwordInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") signIn();
});

// --- Init ---
async function init() {
  const stored = await chrome.storage.local.get(["authToken", "authUsername"]);
  if (stored.authToken && stored.authUsername) {
    authToken = stored.authToken;
    authUsername = stored.authUsername;
    showLoggedIn();
    checkStatus();
  } else {
    showLoggedOut();
  }
}

init();
