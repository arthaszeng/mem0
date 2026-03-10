"use client";

import { useEffect } from "react";
import { Provider, useDispatch } from "react-redux";
import { store } from "../store/store";
import { setUserId } from "@/store/profileSlice";
import { USER_COOKIE, TOKEN_COOKIE, getCookie, decodeJwtPayload } from "@/lib/auth";

function AuthInit({ children }: { children: React.ReactNode }) {
  const dispatch = useDispatch();

  useEffect(() => {
    const token = getCookie(TOKEN_COOKIE);
    if (token) {
      const payload = decodeJwtPayload(token);
      if (payload?.username) {
        dispatch(setUserId(payload.username));
        return;
      }
    }
    const user = getCookie(USER_COOKIE);
    if (user) {
      dispatch(setUserId(user));
    }
  }, [dispatch]);

  return <>{children}</>;
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <Provider store={store}>
      <AuthInit>{children}</AuthInit>
    </Provider>
  );
}
