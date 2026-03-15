import { NextResponse } from "next/server";

export async function POST() {
  return NextResponse.json(
    { error: "Login is now handled by /auth/login via the auth service" },
    { status: 410 },
  );
}
