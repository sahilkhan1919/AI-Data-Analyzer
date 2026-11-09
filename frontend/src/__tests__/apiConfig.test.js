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

  it("uses an explicitly configured API URL during development", () => {
    expect(
      resolveApiUrl({
        apiUrl: "https://api.example.test/",
        mode: "development",
        location: { protocol: "https:", hostname: "dashboard.example.test" },
      })
    ).toBe("https://api.example.test");
  });

  it("uses same-origin requests in production when no API URL is configured", () => {
    expect(
      resolveApiUrl({
        apiUrl: "",
        mode: "production",
        location: { protocol: "https:", hostname: "dashboard.example.test" },
      })
    ).toBe("");
  });

  it("rejects an external API URL in production", () => {
    expect(() =>
      resolveApiUrl({
        apiUrl: "https://api.example.test",
        mode: "production",
        location: { protocol: "https:", hostname: "dashboard.example.test" },
      })
    ).toThrow(/VITE_API_URL must be unset in production/);
  });

  it("rejects localhost API URLs in development", () => {
    expect(() =>
      resolveApiUrl({
        apiUrl: "http://localhost:5001",
        mode: "development",
        location: { protocol: "https:", hostname: "dashboard.example.test" },
      })
    ).toThrow(/without credentials or localhost/);
  });
});
