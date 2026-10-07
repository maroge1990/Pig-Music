/** Shared transport: deduplicate concurrent reads, clone responses for callers,
 * and invalidate reads after successful mutations. No browser credential cache.
 */
const reads = new Map<string, Promise<Response>>();
let libraryRead: Promise<unknown> | undefined;
let libraryResponse: Response | undefined;
let artworkRevision: number | undefined;

export async function apiFetch(
  path: string,
  options?: RequestInit,
): Promise<Response> {
  const method = options?.method?.toUpperCase() || "GET";
  const headers = new Headers(options?.headers);
  if (method !== "GET" && method !== "HEAD") headers.set("X-Pig-Request", "1");
  options = { ...options, headers, credentials: "same-origin" };

  if (method !== "GET" || options?.signal) {
    const response = await readResponse(path, options);
    if (
      response.ok &&
      method !== "GET" &&
      path !== "/api/membership" &&
      !(
        path === "/api/favourites" &&
        options?.body &&
        !String(options.body).includes('"favourite":')
      )
    ) {
      reads.clear();
      libraryRead = undefined;
    }
    return response;
  }
  let read = reads.get(path);
  if (!read) {
    read = readResponse(path, options);
    reads.set(path, read);
    const current = read;
    void read
      .finally(() => {
        if (reads.get(path) === current) reads.delete(path);
      })
      .catch(() => {});
  }
  return (await read).clone();
}

export class ApiError extends Error {
  public code: string;
  constructor(message: string, code: string) {
    super(message);
    this.code = code;
  }
}
const accountErrors: Record<string, string> = {
  invalid_credentials: "The username or password is incorrect.",
  authentication_required: "Please sign in to continue.",
  setup_required: "The administrator needs to finish the first account setup.",
  https_required: "Open Pig Music using its private HTTPS address.",
  rate_limited: "Too many attempts. Please wait before trying again.",
  invalid_setup_code:
    "The setup code has expired or was already used. Ask your administrator for a new code.",
  username_unavailable: "That username is already in use.",
  weak_password: "Choose a password between 12 and 256 characters.",
};

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await apiFetch("/api" + path, options);
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    let code = "request_failed";
    try {
      const body = await response.json();
      code = body.code || "request_failed";
      if (typeof body.detail === "string")
        message = accountErrors[code] || body.detail;
    } catch {
      /* Keep a readable response for non-JSON failures. */
    }
    throw new ApiError(message, code);
  }
  return response.json();
}

export function cachedLibrary<T>(): Promise<T> {
  libraryRead ||= api("/v1/library").catch((error) => {
    libraryRead = undefined;
    throw error;
  });
  return libraryRead as Promise<T>;
}

export function rememberLibrary(library: unknown) {
  libraryRead = Promise.resolve(library);
}

window.addEventListener("music-library-changed", () => {
  libraryRead = undefined;
});

async function readResponse(
  path: string,
  options?: RequestInit,
): Promise<Response> {
  if (path !== "/api/library" || (options?.method && options.method !== "GET"))
    return transport(path, options);
  const headers = new Headers(options?.headers);
  const etag = libraryResponse?.headers.get("etag");
  if (etag) headers.set("If-None-Match", etag);
  const response = await transport(path, { ...options, headers });
  if (response.status === 304 && libraryResponse)
    return libraryResponse.clone();
  if (response.ok) libraryResponse = response.clone();
  return response;
}

export function updateArtworkRevision(revision: number | undefined) {
  if (revision === undefined || revision === artworkRevision) return;
  artworkRevision = revision;
  window.dispatchEvent(new Event("music-artwork-changed"));
}

// One retry clock for missing images; successful immutable images stay cached.
setInterval(() => {
  if (!document.hidden) window.dispatchEvent(new Event("music-artwork-retry"));
}, 60000);

export function clearSessionReads() {
  reads.clear();
  libraryRead = undefined;
  libraryResponse = undefined;
}

async function transport(path: string, options?: RequestInit) {
  const response = await fetch(path, options);
  if (response.status === 401) {
    clearSessionReads();
    window.dispatchEvent(new Event("music-auth-required"));
  }
  if (response.status === 403)
    window.dispatchEvent(
      new CustomEvent("music-forbidden", {
        detail: "You do not have access to that action.",
      }),
    );
  return response;
}
