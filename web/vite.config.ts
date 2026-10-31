/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { execSync } from "node:child_process";

// Версия интерфейса: коммит, из которого собран фронт. Нет git: «неизвестно».
function gitInfo(): { commit: string; date: string } {
  try {
    const out = execSync("git log -1 --format=%h|%cI", { encoding: "utf8" }).trim();
    const [commit, date] = out.split("|");
    return { commit: commit || "неизвестно", date: date || "" };
  } catch {
    return { commit: "неизвестно", date: "" };
  }
}
const build = gitInfo();

export default defineConfig({
  // Build-time базовый путь: VITE_BASE=/agent/ (режим IP) или "/" (домен/dev).
  base: process.env.VITE_BASE ?? "/",
  define: {
    __APP_COMMIT__: JSON.stringify(build.commit),
    __APP_COMMIT_DATE__: JSON.stringify(build.date),
  },
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
