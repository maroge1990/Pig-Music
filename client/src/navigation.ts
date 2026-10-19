/** Where a catalogue artist opens. From the library it stays under Library
 * (`#/library/discography/…`) so the nav keeps its highlight; otherwise it is
 * a Search page. Pages already under Library keep that form. */
export function discoverUrl(
  artist: { id: string; name: string },
  releaseId?: string,
  from: "library" | "search" = location.hash.startsWith("#/library/")
    ? "library"
    : "search",
) {
  const parameters = new URLSearchParams({ name: artist.name });
  if (releaseId) parameters.set("release", releaseId);
  return from === "library"
    ? `/library/discography/${artist.id}?${parameters}`
    : `/search/artist/${artist.id}?${parameters}`;
}
