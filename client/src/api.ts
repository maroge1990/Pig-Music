/** Shared transport: deduplicate concurrent reads, clone responses for callers,
 * and invalidate reads after successful mutations. No browser credential cache.
 */
const reads = new Map<string, Promise<Response>>();
let libraryRead: Promise<unknown> | undefined;

export async function apiFetch(
  path: string,
  options?: RequestInit,
): Promise<Response> {
  const method = options?.method?.toUpperCase() || "GET";
  if (method !== "GET" || options?.signal) {
    const response = await fetch(path, options);
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
    read = fetch(path, options);
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

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await apiFetch("/api" + path, options);
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* Keep a readable response for non-JSON failures. */
    }
    throw new Error(message);
  }
  return response.json();
}

export function cachedLibrary<T>(): Promise<T> {
  libraryRead ||= api("/library").catch((error) => {
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
