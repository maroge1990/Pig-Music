import { useEffect, useState } from "react";
import { api } from "./api";
import type { Person } from "./AppShell";

type InboxAlbum = {
  id: string;
  title: string;
  artist: string;
  tracks: { id: string }[];
};
type Activity = { at: number; display_name?: string; event: string };

function json(body: unknown) {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

/** Shared loading/notice state for the administrator account screens. */
function useAdminData(inboxOffset = 0) {
  const [people, setPeople] = useState<Person[]>([]);
  const [events, setEvents] = useState<Activity[]>([]);
  const [inbox, setInbox] = useState<InboxAlbum[]>([]);
  const [inboxNext, setInboxNext] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function load() {
    setPeople((await api<{ people: Person[] }>("/v1/people")).people);
    setEvents(
      (await api<{ events: Activity[] }>("/v1/people/activity")).events,
    );
    const page = await api<{
      albums: InboxAlbum[];
      next_offset: number | null;
    }>(`/v1/admin/unassigned?offset=${inboxOffset}`);
    setInbox(page.albums);
    setInboxNext(page.next_offset);
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
  const notices = (
    <>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
    </>
  );
  return { people, events, inbox, inboxNext, action, notices };
}

export function AdminPeople() {
  const { people, events, action, notices } = useAdminData();
  const [code, setCode] = useState("");
  return (
    <>
      {notices}
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
            One-use setup code: <strong>{code}</strong>. It expires in 24 hours.{" "}
            <button onClick={() => setCode("")}>Hide code</button>
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
  );
}

export function UnassignedMusic() {
  const [inboxOffset, setInboxOffset] = useState(0);
  const { people, inbox, inboxNext, action, notices } =
    useAdminData(inboxOffset);
  return (
    <>
      {notices}
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
    </>
  );
}
