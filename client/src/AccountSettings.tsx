import { useEffect, useState } from "react";
import { api } from "./api";
import type { Person } from "./AccountsShell";

type Session = {
  id: string;
  device_name: string;
  platform: string;
  revoked_at: number | null;
};
type InboxAlbum = {
  id: string;
  title: string;
  artist: string;
  tracks: { id: string }[];
};
export function AccountSettings({ user }: { user: Person }) {
  const [quality, setQuality] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [events, setEvents] = useState<
    { at: number; display_name?: string; event: string }[]
  >([]);
  const [inbox, setInbox] = useState<InboxAlbum[]>([]);
  const [inboxOffset, setInboxOffset] = useState(0);
  const [inboxNext, setInboxNext] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [code, setCode] = useState("");
  const [plex, setPlex] = useState<{ configured: boolean; label?: string }>({
    configured: false,
  });
  async function load() {
    const preferences = await api<{
      preferences: { scope: string; item_id: string; preferred: string }[];
    }>("/v1/quality");
    setQuality(
      preferences.preferences.find((p) => p.scope === "system")?.preferred ||
        "",
    );
    setSessions(
      (await api<{ sessions: Session[] }>("/v1/me/sessions")).sessions,
    );
    setPlex(await api("/v1/plex"));
    if (user.role === "owner") {
      setPeople((await api<{ people: Person[] }>("/v1/people")).people);
      setEvents(
        (await api<{ events: typeof events }>("/v1/people/activity")).events,
      );
      const page = await api<{
        albums: InboxAlbum[];
        next_offset: number | null;
      }>(`/v1/admin/unassigned?offset=${inboxOffset}`);
      setInbox(page.albums);
      setInboxNext(page.next_offset);
    }
  }
  useEffect(() => {
    void load().catch((e) => setError(e.message));
  }, [inboxOffset]);
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
      <h1>Your account</h1>
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
        <label>
          Preferred quality
          <select
            value={quality}
            onChange={(e) =>
              void action(() =>
                api("/v1/quality", {
                  ...json({
                    scope: "system",
                    preferred: e.target.value || null,
                  }),
                  method: "PUT",
                }),
              )
            }
          >
            <option value="">Use household default</option>
            <option value="mp3_128">MP3 128</option>
            <option value="mp3_320">MP3 320</option>
            <option value="aac_256">AAC 256</option>
            <option value="lossless">Lossless</option>
          </select>
        </label>
      </section>
      <section className="account-section">
        <h2>Your Plex account</h2>
        <p>
          {plex.configured
            ? `Connected: ${plex.label}`
            : "Connect your Plex account to export your personal playlists and favourites."}
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const d = new FormData(form);
            void action(
              () =>
                api("/v1/plex", {
                  ...json({ token: d.get("token"), label: d.get("label") }),
                  method: "PUT",
                }),
              "Plex account saved",
            ).then(() => form.reset());
          }}
        >
          <label>
            Plex account label
            <input
              name="label"
              required
              maxLength={128}
              defaultValue={user.display_name}
            />
          </label>
          <label>
            Plex token
            <input
              name="token"
              type="password"
              required
              maxLength={512}
              autoComplete="off"
            />
          </label>
          <button type="submit">Save Plex account</button>
        </form>
      </section>
      {user.role === "owner" && (
        <>
          <section className="account-section">
            <h2>People</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const d = new FormData(form);
                void action(async () => {
                  const result = await api<{ code: string }>(
                    "/v1/people",
                    json({
                      username: d.get("username"),
                      display_name: d.get("name"),
                    }),
                  );
                  setCode(result.code);
                  form.reset();
                }, "Person added");
              }}
            >
              <label>
                Name
                <input name="name" required maxLength={128} />
              </label>
              <label>
                Username
                <input name="username" required minLength={2} maxLength={64} />
              </label>
              <button type="submit">Add person</button>
            </form>
            {code && (
              <p role="status">
                One-use setup code: <strong>{code}</strong>. It expires in 24
                hours. <button onClick={() => setCode("")}>Hide code</button>
              </p>
            )}
            {people.map((p) => (
              <p key={p.id}>
                {p.display_name} · {p.role}
                {p.role !== "owner" && (
                  <>
                    <button
                      onClick={() =>
                        void action(
                          async () =>
                            setCode(
                              (
                                await api<{ code: string }>(
                                  `/v1/people/${p.id}/setup-code`,
                                  { method: "POST" },
                                )
                              ).code,
                            ),
                          "New setup code created",
                        )
                      }
                    >
                      Reset password
                    </button>
                    <button
                      onClick={() =>
                        void action(
                          () =>
                            api(`/v1/people/${p.id}/disabled`, {
                              ...json({ disabled: !p.disabled }),
                              method: "PUT",
                            }),
                          p.disabled ? "Account enabled" : "Account disabled",
                        )
                      }
                    >
                      {p.disabled ? "Enable" : "Disable"}
                    </button>
                  </>
                )}
              </p>
            ))}
          </section>
          <section className="account-section">
            <h2>Unassigned music</h2>
            <p>
              Newly scanned music waits here until you choose whose library it
              belongs in.
            </p>
            {!inbox.length && <p>No music is waiting for assignment.</p>}
            {inbox.map((a) => (
              <form
                key={a.id}
                onSubmit={(e) => {
                  e.preventDefault();
                  const d = new FormData(e.currentTarget);
                  void action(
                    () =>
                      api(
                        "/v1/admin/unassigned/assign",
                        json({
                          track_ids: a.tracks.map((t) => t.id),
                          user_ids: d.getAll("person"),
                        }),
                      ),
                    "Music assigned",
                  );
                }}
              >
                <h3>
                  {a.title} · {a.artist}
                </h3>
                {people
                  .filter((p) => !p.disabled)
                  .map((p) => (
                    <label key={p.id}>
                      <input type="checkbox" name="person" value={p.id} />
                      {p.display_name}
                    </label>
                  ))}
                <button type="submit">Assign {a.tracks.length} songs</button>
              </form>
            ))}
            <button
              disabled={!inboxOffset}
              onClick={() => setInboxOffset(Math.max(0, inboxOffset - 100))}
            >
              Previous
            </button>
            <button
              disabled={inboxNext === null}
              onClick={() => setInboxOffset(inboxNext || 0)}
            >
              Next
            </button>
          </section>
          <section className="account-section">
            <h2>Account activity</h2>
            {events.map((e, i) => (
              <p key={i}>
                {new Date(e.at * 1000).toLocaleString()} ·{" "}
                {e.display_name || "Unknown account"} ·{" "}
                {e.event.replaceAll("_", " ")}
              </p>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
