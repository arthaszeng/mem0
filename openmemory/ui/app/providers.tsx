"use client";

import { useEffect } from "react";
import { Provider, useDispatch } from "react-redux";
import { store } from "../store/store";
import { setUserId } from "@/store/profileSlice";
import { USER_COOKIE_NAME } from "@/lib/auth";

function AuthInit({ children }: { children: React.ReactNode }) {
  const dispatch = useDispatch();

  useEffect(() => {
    const match = document.cookie
      .split("; ")
      .find((c) => c.startsWith(`${USER_COOKIE_NAME}=`));
    if (match) {
      const username = decodeURIComponent(match.split("=")[1]);
      if (username) {
        dispatch(setUserId(username));
      }
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
