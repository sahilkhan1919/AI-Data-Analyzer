import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const config = JSON.parse(
  readFileSync(resolve(process.cwd(), "vercel.json"), "utf8")
);

describe("Vercel API proxy", () => {
  it("rewrites all frontend API paths to the Render backend without method filtering", () => {
    const rewrites = new Map(
      config.rewrites.map(({ source, destination }) => [source, destination])
    );
    const backend = "https://ai-data-analyzer-backend.onrender.com";

    expect(rewrites.get("/api/:path*")).toBe(`${backend}/api/:path*`);
    expect(rewrites.get("/upload")).toBe(`${backend}/upload`);
    expect(rewrites.get("/chart-data")).toBe(`${backend}/chart-data`);
    expect(rewrites.get("/insights")).toBe(`${backend}/insights`);
    expect(rewrites.get("/ask")).toBe(`${backend}/ask`);
    expect(rewrites.get("/download/:path*")).toBe(`${backend}/download/:path*`);
    expect(config.rewrites.every((rewrite) => !rewrite.methods)).toBe(true);
  });
});
