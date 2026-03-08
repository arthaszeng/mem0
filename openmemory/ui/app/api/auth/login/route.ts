import { NextRequest, NextResponse } from "next/server";
import {
  createSessionToken,
  COOKIE_NAME,
  TOKEN_EXPIRY_MS,
} from "@/lib/auth";

export async function POST(req: NextRequest) {
  const { username, password } = await req.json();

  const validUser = process.env.AUTH_USERNAME;
  const validPass = process.env.AUTH_PASSWORD;
  const secret = process.env.AUTH_SECRET;

  if (!validUser || !validPass || !secret) {
    return NextResponse.json(
      { error: "Auth not configured on server" },
      { status: 500 },
    );
  }

  if (username !== validUser || password !== validPass) {
    return NextResponse.json(
      { error: "Invalid username or password" },
      { status: 401 },
    );
  }

  const token = await createSessionToken(username, secret);

  const res = NextResponse.json({ success: true });
  res.cookies.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: req.headers.get("x-forwarded-proto") === "https",
    sameSite: "lax",
    path: "/",
    maxAge: TOKEN_EXPIRY_MS / 1000,
  });
  return res;
}
