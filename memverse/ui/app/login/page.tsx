"use client";

import { useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import Image from "next/image";
import { TOKEN_COOKIE, USER_COOKIE, setCookie, decodeJwtPayload } from "@/lib/auth";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

export default function LoginPage() {
  const searchParams = useSearchParams();
  const redirectUrl = searchParams.get("redirect");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || data.error || "Login failed");
        setLoading(false);
        return;
      }

      const data = await res.json();
      const payload = decodeJwtPayload(data.access_token);
      const maxAge = data.expires_in || 3600;

      setCookie(TOKEN_COOKIE, data.access_token, maxAge);
      setCookie(USER_COOKIE, payload?.username || username, maxAge);

      const target = data.must_change_password
        ? `${basePath}/change-password`
        : redirectUrl || `${basePath}/`;
      window.location.href = target;
    } catch {
      setError("Network error");
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-zinc-950">
      <div className="w-full max-w-sm space-y-8 px-6">
        <div className="flex flex-col items-center gap-3">
          <Image
            src={`${basePath}/logo.svg`}
            alt="Memverse"
            width={48}
            height={48}
          />
          <h1 className="text-2xl font-semibold text-white">Memverse</h1>
          <p className="text-sm text-zinc-400">Sign in to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="username" className="text-zinc-300">
              Username
            </Label>
            <Input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="border-zinc-700 bg-zinc-900 text-white placeholder:text-zinc-500 focus-visible:ring-purple-500"
              placeholder="Enter username"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="password" className="text-zinc-300">
              Password
            </Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="border-zinc-700 bg-zinc-900 text-white placeholder:text-zinc-500 focus-visible:ring-purple-500"
              placeholder="Enter password"
              required
            />
          </div>

          {error && (
            <p className="text-sm text-red-400 text-center">{error}</p>
          )}

          <Button
            type="submit"
            disabled={loading}
            className="w-full bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50"
          >
            {loading ? "Signing in..." : "Sign in"}
          </Button>
        </form>
      </div>
    </div>
  );
}
