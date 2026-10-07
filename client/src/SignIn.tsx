import { useState } from "react";
import { api } from "./api";

export function SignIn({
  signedIn,
  initialError,
}: {
  signedIn: () => void;
  initialError: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initialError);
  const [setup, setSetup] = useState(location.hash.startsWith("#/setup"));
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
                } else signedIn();
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
}
