/** One hash router for the whole app. Only AppShell listens for changes;
 * views receive the parsed route so nested screens cannot replace each other.
 */
export type Section = "home" | "search" | "library" | "account" | "admin";

export type Route = {
  section: Section;
  /** Path segments after the section, e.g. ["album", "<id>"]. */
  parts: string[];
  params: URLSearchParams;
};

const sections: Section[] = ["home", "search", "library", "account", "admin"];

// Addresses from the pre-accounts interface now live in the Admin section.
const moved: Record<string, string> = {
  queue: "admin/downloads",
  system: "admin/overview",
  migration: "admin/migration",
};

export function parseRoute(hash = location.hash): Route {
  const [rawPath, query] = hash.replace(/^#\/?/, "").split("?");
  const path = moved[rawPath] || rawPath;
  const [first, ...parts] = path.split("/").filter(Boolean);
  const section = sections.includes(first as Section)
    ? (first as Section)
    : "home";
  return {
    section,
    parts: section === first ? parts : [],
    params: new URLSearchParams(query),
  };
}

export function go(path: string) {
  location.hash = path;
}
