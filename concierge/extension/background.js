/**
 * Concierge Cookie Bridge — Chrome Extension background service worker.
 *
 * Listens for messages from the MCP OAuth authorize page and responds
 * with the Concierge access_token cookie (httpOnly, so only readable
 * via the chrome.cookies API).
 */

chrome.runtime.onMessageExternal.addListener(
  (message, sender, sendResponse) => {
    if (message?.type !== "GET_CONCIERGE_COOKIES") {
      sendResponse({ ok: false, error: "Unknown message type" });
      return true;
    }

    // Use url-based matching to capture cookies from any parent domain
    chrome.cookies.getAll(
      { url: "https://concierge.sanofi.com/" },
      (cookies) => {
        if (chrome.runtime.lastError) {
          sendResponse({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }

        const token = cookies.find((c) => c.name === "access_token");
        if (token) {
          sendResponse({ ok: true, access_token: token.value });
          return;
        }

        // Fallback: return all cookie names for debugging
        const names = cookies.map((c) => c.name).join(", ");
        sendResponse({
          ok: false,
          error: `No access_token cookie found. Available cookies: [${names}]`,
        });
      }
    );

    return true; // keep the message channel open for async sendResponse
  }
);
