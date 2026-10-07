import { useEffect, useState, type ReactNode } from "react";
import { api, ApiError, clearSessionReads } from "./api";
import { PersonalLibrary } from "./PersonalLibrary";
import { AccountSettings } from "./AccountSettings";
import "./accounts.css";
import { Home } from "./Home";
import { FirstRun } from "./FirstRun";

export type Person = {
  id: string;
  username: string;
  display_name: string;
  role: "owner" | "member";
  disabled?: boolean;
};
export function AccountsShell({ legacyTools }: { legacyTools: ReactNode }) {
  const [user, setUser] = useState<Person | null>(null);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [firstRun, setFirstRun] = useState(false);
  const [error, setError] = useState("");
  const [page, setPage] = useState(
    location.hash.startsWith("#/library") ||
      location.hash.startsWith("#/search")
      ? "library"
      : "home",
  );
  useEffect(() => {
    const route = () => {
      if (location.hash.startsWith("#/home")) setPage("home");
      else if (
        location.hash.startsWith("#/library") ||
        location.hash.startsWith("#/search")
      )
        setPage("library");
    };
    window.addEventListener("hashchange", route);
    return () => window.removeEventListener("hashchange", route);
  }, []);
  const [setup, setSetup] = useState(location.hash.startsWith("#/setup"));
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
  if (!ready)
    return (
      <main className="account-shell">
        <p role="status">Loading your account…</p>
      </main>
    );
  if (!user)
    if (firstRun)
      return (
        <FirstRun
          complete={() => {
            setFirstRun(false);
            void refresh();
          }}
        />
      );
  if (!user)
    return (
      <main className="account-shell">
        <section className="sign-in-card">
          <div className="account-halo" aria-hidden="true" />
          <img src="/brand/mark.png" alt="" className="account-pig" />
          <span className="account-wordmark" role="img" aria-label="Pig Music">
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
          <h1>{setup ? "Set up your account" : "Your music, together"}</h1>
          <p>
            {setup
              ? "Enter the setup code from your administrator and choose a password."
              : "Sign in to your personal library."}
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const form = e.currentTarget;
              const fields = new FormData(form);
              setError("");
              setBusy(true);
              void api(setup ? "/v1/setup" : "/v1/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(
                  setup
                    ? {
                        code: fields.get("code"),
                        password: fields.get("password"),
                      }
                    : {
                        username: fields.get("username"),
                        password: fields.get("password"),
                      },
                ),
              })
                .then(() => {
                  form.reset();
                  if (setup) {
                    setSetup(false);
                    setError(
                      "Account ready. Sign in with your username and new password.",
                    );
                  } else void refresh();
                })
                .catch((e) => setError(e.message))
                .finally(() => setBusy(false));
            }}
          >
            {setup ? (
              <label>
                Setup code
                <input
                  name="code"
                  required
                  autoComplete="one-time-code"
                  maxLength={64}
                />
              </label>
            ) : (
              <label>
                Username
                <input
                  name="username"
                  required
                  autoComplete="username"
                  maxLength={64}
                />
              </label>
            )}
            <label>
              Password
              <input
                name="password"
                type="password"
                required
                minLength={setup ? 12 : undefined}
                autoComplete={setup ? "new-password" : "current-password"}
                maxLength={256}
              />
            </label>
            <button className="primary-button" type="submit" disabled={busy}>
              {setup ? "Create account" : "Sign in"}
            </button>
          </form>
          <button
            className="text-button"
            onClick={() => {
              setSetup(!setup);
              setError("");
            }}
          >
            {setup ? "Back to sign in" : "Have a setup code?"}
          </button>
          {error && <p role="alert">{error}</p>}
        </section>
      </main>
    );
  return (
    <div className="personal-app">
      <header className="personal-header">
        <a href="#/library" onClick={() => setPage("library")}>
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
        <span>{user.display_name}</span>
        <nav aria-label="Account navigation">
          <button
            onClick={() => {
              location.hash = "/home";
              setPage("home");
            }}
          >
            Home
          </button>
          <button
            onClick={() => {
              location.hash = "/library";
              setPage("library");
            }}
          >
            Library
          </button>
          <button onClick={() => setPage("account")}>Account</button>
          {user.role === "owner" && (
            <button onClick={() => setPage("tools")}>System tools</button>
          )}
          <button
            onClick={() =>
              void api("/v1/auth/logout", { method: "POST" }).then(() => {
                clearSessionReads();
                window.dispatchEvent(new Event("music-signed-out"));
                setUser(null);
                setPage("library");
              })
            }
          >
            Sign out
          </button>
        </nav>
      </header>
      {error && (
        <p className="personal-notice" role="alert">
          {error}
        </p>
      )}
      {page === "home" ? (
        <Home />
      ) : page === "tools" && user.role === "owner" ? (
        legacyTools
      ) : page === "account" ? (
        <AccountSettings user={user} />
      ) : (
        <PersonalLibrary user={user} />
      )}
    </div>
  );
}
