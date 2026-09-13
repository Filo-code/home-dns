# Interim Network Snapshot — 2026-09-13

> **This network is temporary.** It will be replaced by Fastweb Seven Casa 2.5 Gbps with the Internet Box Seven (expected week of 2026-09-20).
> Nothing here should be assumed true for the final network. The final audit is ADR 0001 gates G3–G5.

## Method

- Passive, read-only inspection of one LAN client's own network configuration: a macOS host on Wi-Fi/Ethernet `en0`.
- Tools: `route`, `scutil --dns`, `ipconfig getpacket`, `ipconfig getv6packet`, `ndp -rn`, `arp -an` (existing cache only).
- No scanning. A proposed LAN ping sweep was declined by the owner and not run.
- Public IPv6 prefix and MAC addresses are redacted.

## Findings (CURRENT interim network)

| Item | Observed |
|---|---|
| IPv4 subnet | 192.168.1.0/24 |
| IPv4 gateway | 192.168.1.1 |
| DHCPv4 server | 192.168.1.1 |
| DHCPv4 DNS option | 192.168.1.1 (router) |
| DHCPv4 domain | `lan` |
| DHCPv4 lease time | 43200 s (12 h) |
| IPv6 | Native; global /64 from the Fastweb range `2001:b07::/32` (prefix redacted) |
| IPv6 ULA | `fd59:b8c1:b09a::/64` |
| Router Advertisement flags | `M` + `O` (managed + other config), so stateful DHCPv6 |
| DHCPv6 DNS | `fd59:b8c1:b09a::1` (router ULA) |
| Client IPv6 addresses | SLAAC stable-privacy + temporary addresses + DHCPv6 address |
| Router MAC OUI | Recorded; not confirmed which device model it belongs to |
| Raspberry Pi location | Not identified (not in the client's ARP cache) |

## Implications for the design (to re-check on the Box Seven)

1. **The router advertises its own IPv6 DNS server.** Pointing only IPv4 DNS at the Pi would let clients bypass it over IPv6 (ADR 0001 risk K3).
2. **Clients hold rotating temporary IPv6 addresses.** Per-device identification over IPv6 will be unreliable (ADR 0001 T4, gate G6).

## Not determined

- DHCP range and static reservations
- DNS interception / redirection
- Router admin capabilities
- Ethernet link speeds
- Raspberry Pi addressing
