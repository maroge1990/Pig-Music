import { useEffect, useState } from "react";
import {
  QualitySelect,
  qualityLabel,
  type QualityOption,
} from "./QualitySelect";
import { api } from "./api";
import type { Person } from "./AppShell";
import { PageHeader } from "./PageHeader";

type Session = {
  id: string;
  device_name: string;
  platform: string;
  revoked_at: number | null;
};
export function AccountSettings({
  user,
  signOut,
}: {
  user: Person;
  signOut: () => Promise<void>;
}) {
  const [quality, setQuality] = useState("");
  const [qualityOptions, setQualityOptions] = useState<QualityOption[]>();
  const [household, setHousehold] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function load() {
    const preferences = await api<{
      preferences: { scope: string; item_id: string; preferred: string }[];
      options: QualityOption[];
      household_default: string;
    }>("/v1/quality");
    setQualityOptions(preferences.options);
    setHousehold(preferences.household_default);
    setQuality(
      preferences.preferences.find((p) => p.scope === "system")?.preferred ||
        "",
    );
    setSessions(
      (await api<{ sessions: Session[] }>("/v1/me/sessions")).sessions,
    );
  }
  useEffect(() => {
    void load().catch((e) => setError(e.message));
  }, []);
  async function action(fn: () => Promise<unknown>, text = "Saved") {
    setError("");
    try {
      await fn();
      setMessage(text);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function json(body: unknown) {
    return {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    };
  }
  return (
    <main className="personal-main">
      <PageHeader
        title="Your account"
        subtitle="Appearance, password, devices and your music settings."
      />
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
      <section className="account-section">
        <h2>Appearance</h2>
        <label>
          Theme
          <select
            defaultValue={
              localStorage.getItem("pig-music-appearance") || "system"
            }
            onChange={(e) => {
              const appearance = e.target.value;
              localStorage.setItem("pig-music-appearance", appearance);
              document.documentElement.dataset.theme =
                appearance === "system"
                  ? matchMedia("(prefers-color-scheme: dark)").matches
                    ? "dark"
                    : "light"
                  : appearance;
              void api<{ default_tab: string }>("/v1/preferences")
                .then((p) =>
                  api("/v1/preferences", {
                    ...json({ ...p, appearance }),
                    method: "PUT",
                  }),
                )
                .catch((e) => setError(e.message));
            }}
          >
            <option value="system">System</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>
      </section>
      <section className="account-section">
        <h2>Password</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const d = new FormData(form);
            void action(
              () =>
                api(
                  "/v1/me/password",
                  json({
                    current_password: d.get("current"),
                    password: d.get("password"),
                  }),
                ),
              "Password changed; other sessions were signed out",
            ).then(() => form.reset());
          }}
        >
          <label>
            Current password
            <input
              name="current"
              type="password"
              required
              autoComplete="current-password"
              maxLength={256}
            />
          </label>
          <label>
            New password
            <input
              name="password"
              type="password"
              required
              minLength={12}
              maxLength={256}
              autoComplete="new-password"
            />
          </label>
          <button type="submit">Change password</button>
        </form>
      </section>
      <section className="account-section">
        <h2>Your devices</h2>
        {sessions
          .filter((s) => !s.revoked_at)
          .map((s) => (
            <p key={s.id}>
              {s.device_name} · {s.platform}{" "}
              <button
                onClick={() =>
                  void action(
                    () => api("/v1/me/sessions/" + s.id, { method: "DELETE" }),
                    "Device signed out",
                  )
                }
              >
                Revoke
              </button>
            </p>
          ))}
      </section>
      <section className="account-section">
        <h2>Your music quality</h2>
        <p>
          Shared files retain the highest quality wanted by anyone who holds
          them.
        </p>
        <QualitySelect
          label="Preferred quality"
          value={quality}
          options={qualityOptions}
          inheritLabel={`Use household default${household ? ` (${qualityLabel(household, qualityOptions)})` : ""}`}
          onChange={(value) =>
            void action(() =>
              api("/v1/quality", {
                ...json({ scope: "system", preferred: value || null }),
                method: "PUT",
              }),
            )
          }
        />
      </section>
      <section className="account-section">
        <h2>Sign out</h2>
        <button className="secondary-button" onClick={() => void signOut()}>
          Sign out of PigMusic
        </button>
      </section>
      {user.role === "owner" && (
        <section className="owner-links" aria-label="Admin shortcuts">
          <h2>Admin</h2>
          <p>
            <a href="#/admin/people">People and account activity</a>
            <a href="#/admin/library">Unassigned music</a>
          </p>
        </section>
      )}
    </main>
  );
}
