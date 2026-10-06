# T01: private HTTPS transport foundation

7 October 2026. Owner approved the existing Unraid Tailscale hostname, `https://passyflix.tail6d1471.ts.net`. HTTPS port 443 was unused; the existing 8443 route belongs to another service and must stay intact. PigMusic's proxy target is its existing private address `http://192.168.1.203:8765`, not the roadmap's proposed localhost target.

Implemented: validated bare HTTPS public origin; Uvicorn trusts forwarded protocol only from explicitly configured individual proxy IPs (127.0.0.1 and Unraid 192.168.1.235). Wildcards, broad CIDRs and ambiguous hosts are rejected. Health reports actual interpreted HTTPS. Configured HTTPS Origin is accepted for writes while the same-origin LAN route remains available during physical phone transition; unrelated origins still fail. Native clients need the private HTTPS URL.

145 backend tests pass, including configuration rejection, untrusted spoofed forwarded-protocol headers, HTTPS health and existing LAN transition. Source bundle now includes generated Swift branding inputs for container source verification. Production proxy configuration, certificate/network checks, and both-phone LAN/off-site acceptance remain pending.

Operator configuration after release:

```
/usr/local/sbin/tailscale serve --bg --https=443 http://192.168.1.203:8765
/usr/local/sbin/tailscale serve status --json
```

Use Serve only; no Funnel, public forwarding or DNS exposure. Preserve 8443. Disable only the PigMusic endpoint with `tailscale serve --https=443 off`; never reset the whole Serve configuration. The existing LAN address will not be retired until both phones have passed acceptance.

Reference: [Tailscale Serve command](https://tailscale.com/docs/reference/tailscale-cli/serve), checked against installed CLI help. Account authentication and personal-library scope are later packages; private TLS does not complete them.
