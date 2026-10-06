# T01: private HTTPS transport foundation

7 October 2026. Owner approved the existing Unraid Tailscale hostname, `https://passyflix.tail6d1471.ts.net:10000`. Serve initially appeared to have free port443, but a listener check found the Unraid admin interface there; PigMusic uses port10000. the existing 8443 route belongs to another service and must stay intact. PigMusic's proxy target is its existing private address `http://172.25.0.2:8765`, not the roadmap's proposed localhost target.

Implemented: validated bare HTTPS public origin; Uvicorn trusts forwarded protocol only from explicitly configured individual proxy IPs (127.0.0.1 and existing Docker bridge gateway 172.25.0.1). Wildcards, broad CIDRs and ambiguous hosts are rejected. Health reports actual interpreted HTTPS. Configured HTTPS Origin is accepted for writes while the same-origin LAN route remains available during physical phone transition; unrelated origins still fail. Native clients need the private HTTPS URL.

145 backend tests pass, including configuration rejection, untrusted spoofed forwarded-protocol headers, HTTPS health and existing LAN transition. Source bundle now includes generated Swift branding inputs for container source verification. Production proxy configuration, certificate/network checks, and both-phone LAN/off-site acceptance remain pending.

Operator configuration after release:

```
/usr/local/sbin/tailscale serve --bg --https=10000 http://172.25.0.2:8765
/usr/local/sbin/tailscale serve status --json
```

Use Serve only; no Funnel, public forwarding or DNS exposure. Preserve 8443. Disable only the PigMusic endpoint with `tailscale serve --https=10000 off`; never reset the whole Serve configuration. The existing LAN address will not be retired until both phones have passed acceptance.

Reference: [Tailscale Serve command](https://tailscale.com/docs/reference/tailscale-cli/serve), checked against installed CLI help. Account authentication and personal-library scope are later packages; private TLS does not complete them.


## Delivered release

Live 7 October 2026 as `brand-https-20261007-v1`, immutable image `ghcr.io/maroge1990/pig-music@sha256:37b16f9cdad35bf9dbe013fa8293c90a06a22069d3cda6b15c0dfce4af158e43`, image source revision `6fafc59e2f352139844c810a8929991367c4ab17`. GitHub run37531912504 and exact-image Unraid verification passed 145 tests and artwork/HTTP scale gates. The stopped-state verifier preserved1395 tracks and existing durable rows.

The final runtime-only origin/proxy correction uses port10000 and the existing bridge gateway, recorded in `compose.unraid-preview.yaml`. Host-to-br0 and the pre-existing host-published port are isolated on this Unraid configuration; direct existing bridge172.25.0.2 works. Do not weaken host isolation. Future deployments refresh only this existing PigMusic Serve endpoint to the current bridge address and restore its prior target on rollback.

TLS checks from Unraid validated the certificate without insecure bypass, negotiated HTTP/2, returned health with https:true, and returned PNG/manifest200 with correct MIME types. A matching-Origin write to a nonexistent probe route returned404 (no mutation); an unrelated Origin remains rejected. Serve10000 and8443 are present, no Serve443 or Funnel grant is added; nginx admin443 remains intact. This Mac has no resolvable private hostname/Tailscale installation, so Mac and both-phone LAN/cellular acceptance remains pending. The plain private LAN URL is retained.

Rollback container: `pig-music-preview-before-brand-https-20261007-v1`. Matching stopped-state backup: `/mnt/user/appdata/pig-music-preview/backups/pre-brand-https-20261007-v1`. Prior Serve configuration is retained there as `tailscale-serve-before.json`. The interim compose is preserved with the release inputs; disable only port10000 if reverting to a pre-HTTPS image.
