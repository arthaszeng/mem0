import axios from "axios";
import { TOKEN_COOKIE, getCookie } from "./auth";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8765",
});

api.interceptors.request.use((config) => {
  const token = getCookie(TOKEN_COOKIE);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
