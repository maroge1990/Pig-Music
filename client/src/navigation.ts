export function discoverUrl(
  artist: { id: string; name: string },
  releaseId?: string,
) {
  const parameters = new URLSearchParams({ name: artist.name });
  if (releaseId) parameters.set("release", releaseId);
  return `/search/artist/${artist.id}?${parameters}`;
}
