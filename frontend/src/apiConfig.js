export function validateProductionApiUrl(apiUrl) {
  const configuredUrl = apiUrl?.trim();
  if (!configuredUrl) return "";

  throw new Error(
    "VITE_API_URL must be unset in production. API requests use the same-origin Vercel proxy."
  );
}

function validateExternalApiUrl(apiUrl) {
  const configuredUrl = apiUrl?.trim();
  if (!configuredUrl) return "";

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
  if (configuredUrl) return validateExternalApiUrl(configuredUrl).replace(/\/+$/, "");

  const hostname = location.hostname || "127.0.0.1";
  return `${location.protocol}//${hostname}:5001`;
}
