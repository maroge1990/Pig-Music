> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Saved-library artwork fallback

Status on 5 October 2026: deployed with user approval. All 34 local regression tests passed. Live image: `pig-music:preview-20261005-library-artwork-v2`. Bruce Springsteen’s Greatest Hits artwork was verified as a valid 52,865-byte JPEG on Unraid and cached in appdata. Live queue and download settings were preserved.

## Finding

The snapshot contains no embedded cover for Bruce Springsteen's Greatest Hits. A read-only check of that album's folder and immediate disc directories found no JPG or PNG artwork. The library's previous artwork path relied solely on the embedded images captured in the snapshot. It also chose only the first album for each artist, even when another owned album had artwork.

## Behaviour

Existing embedded images remain first choice. Artist tiles can use another owned album's embedded cover before looking online. Missing album covers resolve lazily from a unique exact artist/title match in MusicBrainz, or an existing unambiguous release ID. Same-titled groups may be disambiguated by a saved year, or a unique year in an exactly named album folder; conflicting hints stay unresolved. The display lookup never assigns catalogue IDs to tracks, changes download matching, writes tags, or modifies source music.

Cover Art Archive images are downloaded into the app's covers directory, decoded, reduced to at most 512 pixels and saved as JPEG. The cache survives restart. Both the artist and album tile reuse this cover. An artist without an embedded cover tries up to three associated albums. Ambiguous matches remain initials; missing matches retry after a day and temporary provider failures after five minutes.

Only artist/album names or existing release IDs are needed for the lookup; music files and listening history are not transmitted. Transfers are restricted to Cover Art Archive and Internet Archive HTTPS hosts, with bounded redirects, a 5 MB limit and image dimension validation. Lazy fetching permits three concurrent cover operations and uses the shared MusicBrainz cache/rate limiter.

Tests verify persistent artist/album cache reuse, unchanged snapshot and queue, another owned album's embedded-cover priority, wrong artist/version rejection, negative caching and rejection of untrusted image redirects. The live Bruce Springsteen check resolved the 1995 group using the album folder, without modifying its missing date tag.
