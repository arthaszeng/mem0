import { NextResponse } from "next/server";

export async function POST() {
  const res = NextResponse.json({ success: true });
  res.cookies.set("om_token", "", { path: "/", maxAge: 0 });
  res.cookies.set("om_user", "", { path: "/", maxAge: 0 });
  return res;
}
