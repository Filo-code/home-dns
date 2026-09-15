# Fastweb Seven B2 audit checklist

> **Status: not yet performed.** Fastweb Seven has not been deployed as the production router/DNS environment. Nothing in this document has been observed or verified — it is the checklist B2 will work through, written in advance so the audit is systematic rather than ad hoc. The audit itself must be **observational only**: no router configuration, DHCP, DNS, firewall, or routing changes.

## Why this exists

The home network has not yet been migrated to Fastweb Seven or to Pi-hole. Before that migration, this checklist needs real answers — from the actual router, not assumptions. This mirrors the existing B1 audit's discipline (`docs/audits/2026-09-14-b1-raspberry-pi-audit.md`): inspect, record, do not change.

## IPv4

- [ ] Public IPv4 vs CGNAT — is the WAN address a real public address, or behind carrier-grade NAT?
- [ ] WAN address (recorded, but see the B1/no-real-network-values convention — a real address belongs in `docs/`, never in `src/`/`config/`).
- [ ] LAN address / subnet Fastweb Seven actually hands out.
- [ ] DHCP server — is it Fastweb Seven's own, and can it be pointed at a different DNS server (i.e. does the router allow overriding the DNS option it advertises via DHCP)?
- [ ] DHCP DNS configuration — what DNS server(s) does Fastweb Seven currently advertise to clients?
- [ ] Can custom DNS actually be advertised (Pi-hole's future address) through Fastweb Seven's DHCP, or does the router force its own?
- [ ] DNS interception/protection — does Fastweb Seven do anything like "DNS protetto" that could intercept or override client DNS settings regardless of DHCP configuration?

## IPv6

- [ ] Global prefix — does Fastweb Seven provide one, and is it stable enough to plan around?
- [ ] Router Advertisements (RA) — confirm what Fastweb Seven actually sends.
- [ ] RDNSS — does the RA include a DNS server option, and can it be overridden?
- [ ] DHCPv6 — is it in use at all, and if so, can its DNS option be changed?
- [ ] DNS servers advertised through IPv6 — record exactly what they are.
- [ ] **Can clients bypass Pi-hole using external IPv6 DNS?** This is the specific, previously-documented risk (see the technology-scouting review, referencing real Pi-hole GitHub issues #2455 and #1512): if Fastweb Seven advertises its own IPv6 DNS servers alongside or instead of Pi-hole's future address, IPv6-capable clients will likely prefer those and silently bypass Pi-hole entirely, even with IPv4 correctly pointed at Pi-hole.

## DNS

- [ ] TCP/UDP 53 — is anything already intercepting or redirecting port 53 traffic at the router?
- [ ] TCP/UDP 853 (DoT) — same question for encrypted DNS transport.
- [ ] DNS-over-HTTPS limitations — does Fastweb Seven do anything (blocking, throttling, or nothing at all) regarding DoH traffic?
- [ ] "DNS protetto" behavior — document exactly what this Fastweb feature does, if enabled, since it's a stated unknown in current planning.

## VPN prerequisites

See `docs/vpn/fastweb-seven-prerequisites.md` for the full VPN-specific checklist (public IPv4/CGNAT, IPv6 reachability, UDP port forwarding, dynamic DNS considerations, firewall behavior). Summarized here for completeness:

- [ ] Inbound IPv4 reachability.
- [ ] Inbound IPv6 reachability.
- [ ] UDP forwarding capability.
- [ ] Port forwarding UI capability and limitations.
- [ ] Dynamic DNS considerations (if the WAN address changes).
- [ ] Firewall behavior beyond simple NAT.

## Rules for this audit

- Observational only. No router changes, no DHCP changes, no DNS changes, no firewall changes, no IPv6 changes.
- Every checked item must cite how it was determined (router admin UI, an external reachability test from outside the LAN, etc.) — never assumed from generic ISP-router behavior or forum posts about a different Fastweb product.
- Real values (WAN address, LAN subnet if it changes from the currently-known `192.168.1.0/24`, etc.) belong in this file or another `docs/` file — never in `src/` or `config/`, per this repository's own guard (`tests/architecture/test_no_real_network_values.py`).
- Once B2 is complete, this checklist should be updated in place (checkboxes ticked, findings recorded) rather than superseded by a second document, so there is one authoritative record.
