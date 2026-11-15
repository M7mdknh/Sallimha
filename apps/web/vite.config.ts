import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api = process.env.SALLIMHA_API_ORIGIN ?? "http://127.0.0.1:8100";
const proxy = Object.fromEntries(
  ["/api", "/healthz", "/readyz", "/webhooks"].map((path) => [path, { target: api, changeOrigin: false }]),
);

// Same-origin console: the dev/preview server proxies API paths to Django.
export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", proxy },
  preview: { host: "127.0.0.1", proxy },
});
