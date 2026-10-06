export type ReleaseGroup = {
  id: string;
  title: string;
  date: string;
  type: string;
  saved_album_id?: string | null;
};
export type Discography = {
  scope: string;
  groups: ReleaseGroup[];
  total: number;
  loading: boolean;
};
export const newestFirst = (a: ReleaseGroup, b: ReleaseGroup) =>
  Number(!a.date) - Number(!b.date) ||
  (b.date || "").localeCompare(a.date || "") ||
  a.title.localeCompare(b.title);
export function mergePage(
  state: Discography,
  scope: string,
  page: ReleaseGroup[],
  total: number,
): Discography {
  if (state.scope !== scope) return state;
  const unique = new Map(state.groups.map((group) => [group.id, group]));
  for (const group of page) unique.set(group.id, group);
  return { ...state, groups: [...unique.values()].sort(newestFirst), total };
}
