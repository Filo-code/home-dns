# VPN architecture — FUTURE, NOT DEPLOYED

> **Status: foundation only.** Nothing described here is installed or running. No WireGuard package is installed on the Raspberry Pi, no port is open, no routing or firewall rule exists. This document and `src/home_dns/config/vpn.py` / `config/vpn/vpn.yaml` exist so the shape is agreed and safe *before* any real implementation. See `docs/vpn/fastweb-seven-prerequisites.md` for what must still be verified (B2) before deployment is even possible.

## 1. Goal

Let a trusted remote device (e.g. a phone off the home Wi-Fi) resolve DNS through the same Pi-hole → Unbound chain the LAN already uses, without exposing Unbound, without becoming the router, and without any change to the current LAN/Fastweb Seven setup.

```
Remote device
     ↓
  WireGuard
     ↓
Raspberry Pi
     ↓
  Pi-hole
     ↓
  Unbound
     ↓
Internet
```

## 2. Three distinct modes — do not conflate them

| Mode | What it gives the client | Status |
|---|---|---|
| **1. DNS-only** | DNS via Pi-hole only; the client's own internet traffic still goes out its normal way | **First target**, once deployed |
| **2. LAN-access** | DNS-only, plus reachability to specific LAN devices/services (`allowed_networks`) | Second step, per-client opt-in (`clients[].allowed_lan`) |
| **3. Full-tunnel** | All of the client's internet traffic routed through the Pi | **Explicitly deferred** — evaluate separately later |

The config schema already distinguishes these (`vpn.allowed_networks`, per-client `allowed_lan`, `vpn.full_tunnel`), but only mode 1 is the intended first real deployment. Do not implement mode 3 as part of the same change that turns on mode 1.

## 3. Network shape

- Dedicated interface (`wg0` by default — see `interface_name` in the config).
- Dedicated subnet, distinct from the LAN's own subnet — `check_no_subnet_conflicts()` in `config/vpn.py` exists specifically to catch an overlap, but it takes the real LAN subnet as an explicit argument rather than a hard-coded constant (this repository's own convention keeps real network identifiers out of `src/`/`config/` — see `tests/architecture/test_no_real_network_values.py`). Before any real deployment, run that check with the LAN subnet `docs/audits/2026-09-14-b1-raspberry-pi-audit.md` records.
- `10.8.0.0/24` is a reasonable, conventional WireGuard subnet choice and does not overlap the LAN subnet observed at B1 — but re-verify this at B2, since Fastweb Seven's own network has not been audited yet and could change what's actually available.
- Pi-hole already listens on `0.0.0.0:53` (confirmed in the Stage C lab), so once a `wg0` interface exists, Pi-hole is automatically reachable on it too — no separate DNS-server configuration is needed for DNS-only mode. This is also exactly why Unbound must stay `127.0.0.1`/`::1`-only: it must never become reachable from `wg0` either.

## 4. Key handling

- WireGuard uses one keypair per peer (server and each client). A private key must **never** be committed, logged, or otherwise leave the device that generated it.
- `config/vpn/vpn.yaml`'s `clients[].public_key` field is validated (`config/vpn.py`) to reject anything that looks like it might be a private key by name, as a cheap sanity check — not a substitute for actual care.
- Real key generation (`wg genkey`, `wg pubkey`) happens only at real deployment time, on the Pi (server key) and on each client device (client key) — never inside this repository, never inside a chat transcript, never inside a config file that gets committed.
- Recommended future secret handling: server private key in a root-only file outside the repo (matching how `pihole.toml`/Unbound config already live outside git); client private keys stay on the client devices entirely — the server only ever needs each client's *public* key.

## 5. Firewall/NAT — documented, not applied

None of the following exists yet. They are what a real deployment will eventually need, recorded here so the decision is made deliberately later, not implemented now:

- A firewall rule allowing inbound UDP to the WireGuard port (commonly 51820, not yet chosen) — currently **no firewall is configured on the Pi at all**, so this is a new thing to add carefully, not a rule to append to an existing ruleset.
- A NAT/port-forward rule on Fastweb Seven for that same UDP port — **not possible to plan concretely until B2** confirms what Fastweb Seven's port-forwarding UI actually supports (see `docs/vpn/fastweb-seven-prerequisites.md`).
- `net.ipv4.ip_forward` (and the IPv6 equivalent) would need enabling on the Pi for LAN-access/full-tunnel modes — not for DNS-only mode, where the Pi never routes the client's other traffic.
- No firewall rule of any kind is part of this foundation phase, per the task's explicit constraint.

## 6. Revocation and client isolation

- Revoking a client is just removing its `[Peer]` block from the server's WireGuard config (and reloading) — WireGuard has no built-in certificate-revocation mechanism, so this is why the `clients` list in `vpn.yaml` is the intended source of truth for "who is currently allowed."
- Client isolation: by default, WireGuard clients can reach the server but not each other unless explicitly routed — the DNS-only mode's design keeps this simple (each client only ever talks to the Pi for port 53).

## 7. Failure modes to design for (not yet implemented)

- If a VPN client's DNS queries somehow bypass the tunnel (misconfigured client), the client silently falls back to its own local network's DNS — this must be a known, accepted limitation communicated to the user of that client, not something the Pi can prevent from the server side.
- If the Pi is unreachable (down, or WireGuard crashed), a DNS-only client has no DNS at all until the client's OS falls back — evaluate whether a client-side fallback resolver is acceptable or whether that itself is a DNS leak to document.

## 8. What "done" looks like for the first real deployment

1. B2 (Fastweb Seven audit) confirms UDP inbound/port-forwarding is actually possible.
2. A real subnet choice is checked against the real LAN subnet with `check_no_subnet_conflicts()`.
3. WireGuard is installed natively (no Docker, matching the rest of this project's native-install convention).
4. Exactly one client, DNS-only mode, is configured and tested from an actual remote network (not just LAN).
5. Only after DNS-only is proven stable does LAN-access get evaluated — full-tunnel is a separate, later decision.

None of steps 1–5 have happened yet.
