import { api } from "./api";
import type { SongReference } from "./SongActions";

type Value = { favourited: boolean; error?: string };
type Subscriber = (value: Value) => void;
const listeners = new Map<string, Set<Subscriber>>();
const references = new Map<string, SongReference>();
const values = new Map<string, Value>();
const pending = new Set<string>();
let scheduled = false;

async function flush() {
  scheduled = false;
  const keys = [...pending];
  pending.clear();
  for (let offset = 0; offset < keys.length; offset += 200) {
    const batch = keys.slice(offset, offset + 200);
    try {
      const result = await api<{ songs: Value[] }>("/membership", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          songs: batch.map((key) => references.get(key)),
        }),
      });
      batch.forEach((key, index) => publish(key, result.songs[index]));
    } catch {
      /* Retry on the next mounted view; no false success indicator. */
    }
  }
}

function publish(key: string, value: Value) {
  values.set(key, value);
  listeners.get(key)?.forEach((listener) => listener(value));
}

export function subscribeSong(song: SongReference, listener: Subscriber) {
  const key = JSON.stringify(song);
  references.set(key, song);
  const subscribers = listeners.get(key) || new Set<Subscriber>();
  subscribers.add(listener);
  listeners.set(key, subscribers);
  const value = values.get(key);
  if (value) listener(value);
  else {
    pending.add(key);
    if (!scheduled) {
      scheduled = true;
      queueMicrotask(() => void flush());
    }
  }
  return () => {
    subscribers.delete(listener);
  };
}

export function updateFavourite(song: SongReference, favourited: boolean) {
  // Different references can denote the same song (player, album, playlist).
  // Reconcile only mounted rows after a favourite mutation, never on playlist add.
  values.clear();
  publish(JSON.stringify(song), { favourited });
  listeners.forEach((subscribers, key) => {
    if (subscribers.size) pending.add(key);
  });
  if (!scheduled) {
    scheduled = true;
    queueMicrotask(() => void flush());
  }
}
