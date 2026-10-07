import { lazy, Suspense, useEffect, useState } from "react";
import {
  House,
  LibraryBig,
  Search,
  ShieldCheck,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { api, ApiError, clearSessionReads } from "./api";
import { PersonalLibrary } from "./PersonalLibrary";
import { AccountSettings } from "./AccountSettings";
import { Home } from "./Home";
import { FirstRun } from "./FirstRun";
import { SignIn } from "./SignIn";
import { ToolBoundary } from "./ToolBoundary";
import { useFixedHeight } from "./useFixedHeight";
import { parseRoute, type Route, type Section } from "./routes";
import "./accounts.css";

const AdminTools = lazy(() =>
  import("./AdminTools").then((m) => ({ default: m.AdminTools })),
);

export type Person = {
  id: string;
  username: string;
  display_name: string;
  role: "owner" | "member";
  disabled?: boolean;
};

const sections: { id: Section; label: string; icon: LucideIcon }[] = [
  { id: "home", label: "Home", icon: House },
  { id: "search", label: "Search", icon: Search },
  { id: "library", label: "Library", icon: LibraryBig },
  { id: "account", label: "Account", icon: UserRound },
  // Administrator additions always follow everything a member sees.
  { id: "admin", label: "Admin", icon: ShieldCheck },
];

export function AppShell() {
  const [user, setUser] = useState<Person | null>(null);
  const [ready, setReady] = useState(false);
  const [firstRun, setFirstRun] = useState(false);
  const [error, setError] = useState("");
  const [route, setRoute] = useState<Route>(() => parseRoute());
  const nav = useFixedHeight("--mobile-nav-height", !!user);

  useEffect(() => {
    const changed = () => {
      setRoute(parseRoute());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);

  async function refresh() {
    try {
      const state = await api<{ setup_required: boolean }>("/v1/setup/owner");
      setFirstRun(state.setup_required);
      if (state.setup_required) {
        setUser(null);
        setError("");
        return;
      }
      setUser(await api<Person>("/v1/me"));
      setError("");
    } catch (e) {
      setUser(null);
      if ((e as ApiError).code === "setup_required")
        setError("The administrator needs to finish the first account setup.");
      else if ((e as ApiError).code !== "authentication_required")
        setError((e as Error).message);
    } finally {
      setReady(true);
    }
  }

  useEffect(() => {
    void refresh();
    const expired = () => {
      setUser(null);
      clearSessionReads();
    };
    const forbidden = () => setError("You do not have access to that action.");
    window.addEventListener("music-auth-required", expired);
    window.addEventListener("music-forbidden", forbidden);
    return () => {
      window.removeEventListener("music-auth-required", expired);
      window.removeEventListener("music-forbidden", forbidden);
    };
  }, []);

  async function signOut() {
    await api("/v1/auth/logout", { method: "POST" });
    clearSessionReads();
    window.dispatchEvent(new Event("music-signed-out"));
    setUser(null);
    location.hash = "/home";
  }

  if (!ready)
    return (
      <main className="account-shell pig-splash app-splash">
        <img src="/brand/mark.png" alt="" className="account-pig" />
        <p role="status">Loading your account…</p>
      </main>
    );
  if (!user && firstRun)
    return (
      <FirstRun
        complete={() => {
          setFirstRun(false);
          void refresh();
        }}
      />
    );
  if (!user)
    return <SignIn signedIn={() => void refresh()} initialError={error} />;

  const owner = user.role === "owner";
  const section = route.section === "admin" && !owner ? "home" : route.section;
  return (
    <div className="personal-app">
      <header className="personal-header">
        <a href="#/home" className="personal-brand">
          <img src="/brand/mark.png" alt="" />
          <span className="header-wordmark" role="img" aria-label="Pig Music">
            <img
              src="/brand/wordmark-light.svg"
              className="light-wordmark"
              alt=""
            />
            <img
              src="/brand/wordmark-dark.svg"
              className="dark-wordmark"
              alt=""
            />
          </span>
        </a>
        <nav ref={nav} className="app-nav" aria-label="Main navigation">
          {sections
            .filter((s) => s.id !== "admin" || owner)
            .map(({ id, label, icon: Icon }) => (
              <a
                key={id}
                href={"#/" + id}
                aria-current={section === id ? "page" : undefined}
              >
                <Icon size={20} aria-hidden="true" />
                <span>{label}</span>
              </a>
            ))}
        </nav>
      </header>
      {error && (
        <p className="personal-notice" role="alert">
          {error}
        </p>
      )}
      {section === "home" ? (
        <Home />
      ) : section === "search" || section === "library" ? (
        <PersonalLibrary user={user} route={{ ...route, section }} />
      ) : section === "account" ? (
        <AccountSettings user={user} signOut={signOut} />
      ) : (
        <ToolBoundary>
          <Suspense
            fallback={
              <main className="personal-main">
                <p role="status">Loading admin…</p>
              </main>
            }
          >
            <AdminTools route={route} />
          </Suspense>
        </ToolBoundary>
      )}
    </div>
  );
}
