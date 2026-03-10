export const COOKIE_NAME = "om_session";
export const USER_COOKIE_NAME = "om_user";
export const TOKEN_EXPIRY_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

async function getHmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
}

async function hmacSign(payload: string, secret: string): Promise<string> {
  const key = await getHmacKey(secret);
  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payload),
  );
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

export async function createSessionToken(
  username: string,
  secret: string,
): Promise<string> {
  const exp = Date.now() + TOKEN_EXPIRY_MS;
  const payload = `${username}|${exp}`;
  const sig = await hmacSign(payload, secret);
  return `${btoa(payload)}.${sig}`;
}

export async function verifySessionToken(
  token: string,
  secret: string,
): Promise<{ valid: boolean; username?: string }> {
  try {
    const dotIdx = token.indexOf(".");
    if (dotIdx === -1) return { valid: false };

    const payloadB64 = token.slice(0, dotIdx);
    const sig = token.slice(dotIdx + 1);
    const payload = atob(payloadB64);

    const expected = await hmacSign(payload, secret);
    if (expected !== sig) return { valid: false };

    const [username, expStr] = payload.split("|");
    if (Date.now() > Number(expStr)) return { valid: false };

    return { valid: true, username };
  } catch {
    return { valid: false };
  }
}
