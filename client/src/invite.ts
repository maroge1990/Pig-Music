/** Pure helpers for invite links. The invite code travels only in the URL
 * fragment, is moved into memory at startup and is scrubbed from the address
 * bar before anything else runs. */

const MAX_CODE = 64;
let pending: string | null = null;

/** The code from `#/join?code=...`, normalised, or null for anything else. */
export function readInvite(hash: string): string | null {
  const match = /^#\/?join\?(.*)$/.exec(hash);
  if (!match) return null;
  const code = new URLSearchParams(match[1]).get("code")?.trim().toUpperCase();
  return code && code.length <= MAX_CODE ? code : null;
}

type Where = { hash: string; pathname: string; search: string };
type Past = { replaceState(data: unknown, unused: string, url: string): void };

/** Keep the invite code in memory and remove it from the visible URL. */
export function captureInvite(
  where: Where = location,
  past: Past = history,
): string | null {
  if (!/^#\/?join\b/.test(where.hash)) return null;
  const code = readInvite(where.hash);
  past.replaceState(null, "", where.pathname + where.search + "#/join");
  if (code) pending = code;
  return code;
}

export const pendingInvite = () => pending;
export const clearInvite = () => {
  pending = null;
};

const HINT = "pig-music-install-hint";

export function markInstallHint() {
  try {
    sessionStorage.setItem(HINT, "1");
  } catch {
    /* storage unavailable: skip the hint */
  }
}
export function installHintPending(): boolean {
  try {
    if (sessionStorage.getItem(HINT) !== "1") return false;
  } catch {
    return false;
  }
  const standalone =
    (typeof matchMedia === "function" &&
      matchMedia("(display-mode: standalone)").matches) ||
    (navigator as { standalone?: boolean }).standalone === true;
  return !standalone;
}
export function dismissInstallHint() {
  try {
    sessionStorage.removeItem(HINT);
  } catch {
    /* nothing to clear */
  }
}

/** "Expires in 24 hours", "Expires in 35 minutes" or "Expired". */
export function expiryText(expiresAt: number, now = Date.now() / 1000) {
  const left = expiresAt - now;
  if (left <= 0) return "Expired";
  if (left < 3600) {
    const m = Math.max(1, Math.round(left / 60));
    return `Expires in ${m} minute${m === 1 ? "" : "s"}`;
  }
  const h = Math.round(left / 3600);
  return `Expires in ${h} hour${h === 1 ? "" : "s"}`;
}

/** One SVG path for every dark module, surrounded by a quiet zone. */
export function qrPath(matrix: boolean[][], quiet = 4) {
  const size = matrix.length + quiet * 2;
  let d = "";
  matrix.forEach((row, y) =>
    row.forEach((dark, x) => {
      if (dark) d += `M${x + quiet} ${y + quiet}h1v1h-1z`;
    }),
  );
  return { size, d };
}

const FRIENDLY: Record<string, string> = {
  invalid_setup_code:
    "This invite has expired or was already used. Ask your administrator for a new one.",
  rate_limited: "Too many attempts. Wait a few minutes and try again.",
};

/** Friendly wording for a failed /v1/setup call. */
export function setupErrorMessage(code: string, message: string) {
  if (FRIENDLY[code]) return FRIENDLY[code];
  if (code === "password_not_accepted")
    return message || "Choose a longer, less common password.";
  return message;
}
