import { describe, expect, it } from "vitest";
import { resolveApiUrl } from "../apiConfig";

describe("resolveApiUrl", () => {
  it("uses the local Flask API during development when no URL is configured", () => {
    expect(
      resolveApiUrl({
        apiUrl: "",
        mode: "development",
        location: { protocol: "http:", hostname: "localhost" },
      })
    ).toBe("http://localhost:5001");
  });

  it("uses an explicitly configured API URL", () => {
    expect(
      resolveApiUrl({
        apiUrl: "https://api.example.test/",
        mode: "production",
        location: { protocol: "https:", hostname: "dashboard.example.test" },
      })
    ).toBe("https://api.example.test");
  });

  it("fails closed when production has no API URL", () => {
    expect(() =>
      resolveApiUrl({
        apiUrl: "",
        mode: "production",
        location: { protocol: "https:", hostname: "dashboard.example.test" },
      })
    ).toThrow(/VITE_API_URL is required for production builds/);
  });

  it("rejects localhost API URLs in production", () => {
    expect(() =>
      resolveApiUrl({
        apiUrl: "http://localhost:5001",
        mode: "production",
        location: { protocol: "https:", hostname: "dashboard.example.test" },
      })
    ).toThrow(/without credentials or localhost/);
  });
});
