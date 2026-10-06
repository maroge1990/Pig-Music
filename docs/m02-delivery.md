# M02: default-deny account integration

7 October 2026. The main app now mounts the HTTPS account router and applies a common authentication dependency to every API route. A startup route audit rejects any route missing that dependency. Before bootstrap, all API calls except health return setup_required; after bootstrap anonymous calls return 401. Public health exposes only status, HTTPS and storage availability.

The interim member policy intentionally permits personal account/session management only. All existing household routes return 403 to members until M03 adds scoped projections. This prevents a partial security release from exposing another person's library, playlists, requests or settings. **Do not deploy this branch as an account cutover before M03/M07 and an interactive owner bootstrap are ready.**

Cookie mutations require HTTPS and X-Pig-Request:1, with existing Origin protection retained. Bearer requests are exempt from the cookie header requirement. Saved playback URLs are HMAC-signed for up to six hours, tied to the issuing session, path and user. Revocation or expiry invalidates them on the next media request; byte ranges remain supported. The signing secret is generated atomically outside Git, persists in appdata and is mode0600; symlinks/bad files fail closed.

Runtime applies credential redaction to access/application logs and strips the explicit legacy-test bypass from the web child environment. Existing functional fixtures deliberately use that bypass in disposable environments; security tests clear it and exercise the real guard across every route. Cookie refresh headers survive explicit file/library response objects.

165 backend tests pass: complete API anonymous/bootstrap walk, member rejection across household/operator routes, missing-guard detection, cookie/Origin mutation checks, signed range playback, path/signature tampering, expiry, revocation and atomic/private secret handling, plus all prior tests. No real credentials were created and no live account cutover occurred.

Router extraction is incremental: accounts are separated; existing application routes remain guarded in the main module. M03 personal-library scope and M07 account screens are next. The production release remains the separate branding/M00/private-HTTPS candidate.
