import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { validateProductionApiUrl } from "./src/apiConfig.js";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  if (mode === "production") validateProductionApiUrl(env.VITE_API_URL);

  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: "./src/setupTests.js"
    }
  };
});