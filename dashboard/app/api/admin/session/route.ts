import { NextResponse } from "next/server";
import { cookies } from "next/headers";

const COOKIE_NAME = "admin_auth";

export const dynamic = "force-dynamic";

export async function GET() {
  const cookieStore = cookies();
  const token = cookieStore.get(COOKIE_NAME);

  if (!token || token.value !== "1") {
    return NextResponse.json({ authorized: false }, { status: 401 });
  }

  return NextResponse.json({ authorized: true });
}

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const password = body?.password as string | undefined;
  const expected = process.env.ADMIN_PASSWORD;

  if (!expected) {
    console.warn("[admin] ADMIN_PASSWORD is not set");
    return NextResponse.json({ error: "未設定管理員密碼" }, { status: 500 });
  }

  if (!password || password !== expected) {
    return NextResponse.json({ error: "密碼錯誤" }, { status: 401 });
  }

  const cookieStore = cookies();
  cookieStore.set(COOKIE_NAME, "1", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/admin",
    maxAge: 60 * 60 * 24 * 30, // 30 days
  });

  return NextResponse.json({ ok: true });
}

