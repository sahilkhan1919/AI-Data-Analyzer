export function validateProductionApiUrl(apiUrl) {
  const configuredUrl = apiUrl?.trim();
  if (!configuredUrl) {
    throw new Error(
      "VITE_API_URL is required for production builds. Set it to the deployed backend URL."
    );
  }

  let parsedUrl;
  try {
    parsedUrl = new URL(configuredUrl);
  } catch {
    throw new Error("VITE_API_URL must be an absolute HTTP(S) backend URL.");
  }

  const hostname = parsedUrl.hostname.toLowerCase().replace(/\.$/, "");
  if (
    !["http:", "https:"].includes(parsedUrl.protocol) ||
    parsedUrl.username ||
    parsedUrl.password ||
    hostname === "localhost" ||
    hostname.endsWith(".localhost") ||
    hostname === "0.0.0.0" ||
    hostname === "::1" ||
    hostname === "[::1]" ||
    /^127(?:\.\d{1,3}){3}$/.test(hostname)
  ) {
    throw new Error(
      "VITE_API_URL must be a public HTTP(S) backend URL without credentials or localhost."
    );
  }

  return configuredUrl.replace(/\/+$/, "");
}

export function resolveApiUrl({ apiUrl, mode, location }) {
  const configuredUrl = apiUrl?.trim();
  if (mode === "production") return validateProductionApiUrl(configuredUrl);
  if (configuredUrl) return configuredUrl.replace(/\/+$/, "");

  const hostname = location.hostname || "127.0.0.1";
  return `${location.protocol}//${hostname}:5001`;
}
