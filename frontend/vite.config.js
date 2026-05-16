import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const apiProxyTarget = "http://127.0.0.1:8011";
const desktopBuild = process.env.AGENT_PLAYGROUND_DESKTOP_BUILD === "1";

export default defineConfig({
  base: desktopBuild ? "./" : "/",
  plugins: [vue()],
  build: desktopBuild
    ? {
        target: "es2015",
        modulePreload: false,
        cssTarget: "chrome61",
      }
    : {},
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
});
