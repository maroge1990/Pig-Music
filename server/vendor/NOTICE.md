# Extracted Music Grabber components

`freemp3cloud.py`, `zvu4no.py`, `jiosaavn.py` and `audio_probe.py` originate from Music Grabber, GitLab `g33kphr33k/musicgrabber`, commit `7fd57573a47ee9d1de0b8331964f294abc68799a` (installed 4.3.0 source comparison recorded in discovery).

The upstream Unlicense is retained in `MUSICGRABBER-LICENSE`. Source parser imports have been redirected to a small local compatibility module. Search errors are raised instead of suppressed so the acquisition worker can report source failures. Original download routines are retained for reference but are not used: Pig Music owns bounded transfers, URL restrictions, cancellation, verification, tagging and publication. No upstream database or user/session code is imported.

`compat.py` is Pig Music code. It provides duration formatting, source timeouts and a neutral search scorer; candidate identity/version matching and file-quality gates are handled by the Pig Music worker.

The JioSaavn search parser also retains upstream album and ISRC fields to check release context before remote playback.
