# Fastweb Seven prerequisites for the VPN — B2 checklist

> **Status: nothing here is verified yet.** Fastweb Seven is not deployed as the production router. Every item below is a question B2 must answer with real observation, not a plan to execute now. See `docs/vpn/architecture.md` for what the VPN itself would look like once these are known.

This is the VPN-specific subset of the full B2 gate — see `docs/audits/fastweb-seven-b2-checklist.md` for the complete network audit checklist (IPv4/IPv6/DNS, not just VPN).

## What must be known before any real WireGuard deployment

### Reachability
- Does Fastweb Seven have a public (non-CGNAT) IPv4 address? If it's behind Fastweb's own CGNAT, inbound WireGuard over IPv4 is not possible without an additional mechanism (a relay, a different ISP product, or IPv6-only inbound).
- Does Fastweb Seven provide a routable, stable-enough IPv6 prefix? If so, inbound over IPv6 may work without any port-forwarding at all (no NAT to traverse) — but requires confirming the Pi's own IPv6 address is reachable from outside and not filtered.
- If IPv4 is usable: does the Fastweb Seven WAN address change often enough that dynamic DNS would be needed to reach it reliably?

### Port forwarding
- Does Fastweb Seven's admin UI expose UDP port forwarding at all, and to what extent (single port, ranges, arbitrary)?
- Is there any indication of "DNS protetto" or similar ISP-level filtering that could interfere with a UDP port being forwarded?
- Are there known Fastweb Seven port-forwarding limitations or quirks documented anywhere (official docs, community reports) that should be planned around?

### Firewall behavior
- Does Fastweb Seven apply any inbound filtering beyond simple NAT (e.g. an integrated firewall/IPS) that could drop or rate-limit unsolicited UDP, even with a forwarding rule configured?
- Is there a way to see, from the router's own admin UI, whether an inbound packet on the forwarded port actually reached the LAN (to distinguish "router problem" from "Pi problem" during setup)?

## What this checklist explicitly does NOT do

- It does not touch Fastweb Seven's configuration. B2 is observational.
- It does not assume any answer above. Every "does Fastweb Seven support X" question here is genuinely open until observed.
- It does not commit to a VPN subnet, port number, or key — those are `docs/vpn/architecture.md` decisions, made only after this checklist is answered.

## Output expected from B2 (for this VPN-specific subset)

A short table: WAN IPv4 type (public/CGNAT), IPv6 prefix (present/absent, and whether it's stable), port-forwarding capability (yes/no/partial), and any observed firewall behavior — each item marked with how it was determined (router UI screenshot, external reachability test, etc.), not assumed.
