> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Apple Music export sample assessment

Inspected 5 October 2026, read-only. Inputs: C:/Users/markr/OneDrive/Favourites.xml and C:/Users/markr/OneDrive/Favourites.txt. No downloads were queued or library changes applied.

## Results

- Both files contain the same 88 tracks, comparing track title, artist and album with duplicate counts preserved. The XML contains one Favourites playlist with 88 ordered references, all resolving to track records.
- The text file is UTF-16 tab-delimited data with Mac line endings. Literal quote characters in names must be preserved; generic CSV quote interpretation would alter the David Bowie Heroes title and album.
- XML is the preferred migration input. Album Artist, Persistent ID, track/disc positions and millisecond duration exist on all 88 records. It also retains playlist membership/order and flags absent from the text columns, including Compilation, Explicit and Favorited where present.
- Both formats contain track names, artists and albums for all records. TXT can remain a secondary input but loses important grouping fields.
- There are 59 distinct track artist names and 71 album groups using album artist plus album name. These counts describe this playlist sample, not the entire household library.
- 87 records have Kind=Apple Music AAC audio file; one has Kind=AAC audio file. No track has a Location field. This demonstrates metadata for cloud/subscription entries without local audio paths; it does not establish availability for download from another source.
- No Apple catalogue track IDs, ISRCs or MusicBrainz album IDs were present in the inspected track fields. Persistent IDs identify source-library items, not globally canonical recordings. Matching needs release context and independent catalogue resolution, with ambiguity preserved for review.

## Agreed compilation classification

13 track records carry Apple's Compilation flag, across 10 album names. Only two of those records use Album Artist=Various Artists. Flags also occur on single-artist greatest-hits albums and on entries labelled as ordinary studio albums. Do not hide every flagged track artist automatically.

The user confirmed that the separate compilations section contains only multi-artist releases. Single-artist best-of/greatest-hits releases stay under their artist. Use album artist, credited performers and release metadata alongside the imported flag; guest/featured artists alone do not establish a multi-artist compilation. Ambiguous classification and corrections remain reviewable.

## Coverage limitation

This validates Favourites as a useful sample and an XML parser target. It does not prove an entire-library export captures every private playlist or all library entries. Validate a full export before claiming migration completeness. Importing this sample alone must produce an inventory with nothing selected for download by default.
