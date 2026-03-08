import { NextRequest, NextResponse } from "next/server";
import { verifySessionToken, COOKIE_NAME } from "@/lib/auth";

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (pathname === "/login" || pathname.startsWith("/api/auth/")) {
    return NextResponse.next();
  }

  const secret = process.env.AUTH_SECRET;
  if (!secret) return NextResponse.next();

  const token = req.cookies.get(COOKIE_NAME)?.value;

  const toLogin = () => {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    return url;
  };

  if (!token) {
    return NextResponse.redirect(toLogin());
  }

  const { valid } = await verifySessionToken(token, secret);
  if (!valid) {
    const res = NextResponse.redirect(toLogin());
    res.cookies.set(COOKIE_NAME, "", { path: "/", maxAge: 0 });
    return res;
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon\\.ico|logo\\.svg|images/).*)",
  ],
};
