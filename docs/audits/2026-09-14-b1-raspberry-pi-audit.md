# Raspberry Pi Audit (B1) — 2026-09-14

> **Scope:** ADR 0001 gates G1 (Raspberry Pi audit) and G2 (real-world resource/performance
> baseline). Read-only inspection of the production Raspberry Pi over SSH. Nothing was
> installed, changed, or configured during this audit — see [../implementation-plan.md](../implementation-plan.md) §4 (Stage B).
>
> **This is the durable record of the B1 findings.** B3 (re-check ADR 0001 against B1/B2 and
> update gate statuses) is expected to read this file rather than conversation history.

## Method

Passive inspection over SSH (`michele@home-dns.local`) of the Pi's own OS, hardware, storage,
network and service state. No packages installed or removed, no configuration files written, no
DNS/network/firewall/systemd changes made.

## Hardware

| Item | Observed |
|---|---|
| Model | Raspberry Pi 4 |
| RAM | 4 GB nominal; ~3.7 GiB total available to the OS; ~3.5 GiB available during the audit |
| CPU | 4-core Cortex-A72 |
| Temperature at audit time | ~40.4°C |
| zram swap | 2 GiB configured, unused at audit time |

## OS

| Item | Observed |
|---|---|
| Distribution | Debian GNU/Linux 13 (trixie), version 13.5 |
| Architecture | ARM64 / aarch64 |
| Kernel | 6.18.34+rpt-rpi-v8 |
| Install style | Raspberry Pi OS Lite (no desktop environment) |
| Hostname | `home-dns` |
| Timezone | Europe/Rome |
| Clock | Synchronized (`systemd-timesyncd` active) |

## Storage

| Item | Observed |
|---|---|
| Media | 32 GB microSD |
| Usable block storage | ~29.7 GB |
| Boot partition | ~512 MB |
| Root filesystem | ext4, ~29.2 GB |
| Root usage at audit time | ~2.1 GB used (~8%), ~26 GB available |
| `/tmp` | Already a tmpfs, ~1.9 GB |

No filesystem errors or degraded-storage signals observed.

## Network

| Item | Observed |
|---|---|
| `eth0` | UP |
| IPv4 | 192.168.1.121/24 (address in use at audit time; static-vs-DHCP-reservation status not yet confirmed) |
| IPv4 gateway | 192.168.1.254 |
| Ethernet link | 1000 Mb/s, full duplex |
| `wlan0` | DOWN (not in use) |
| IPv6 | Enabled; a global IPv6 address was observed on `eth0`, plus a working IPv6 default route (specific address not recorded here — treat as LAN-topology-sensitive, same redaction convention as [2026-09-13-interim-network-snapshot.md](2026-09-13-interim-network-snapshot.md)) |
| NetworkManager | Active (owns interface/DNS configuration) |
| `systemd-networkd` | Inactive |
| Legacy `networking` service | Inactive |

## DNS

| Item | Observed |
|---|---|
| `/etc/resolv.conf` | Generated/managed by NetworkManager |
| Current nameservers | The LAN router (both IPv4 and IPv6) — the Pi is not yet doing any DNS work |
| Pi-hole | **Not installed** |
| Unbound | **Not installed** |
| Port 53 | Free — nothing is listening |
| `dnsmasq-base` | Installed, but **not running as a DNS server**; no active dnsmasq DNS listener. **Do not uninstall it merely because it's present** — it may be a dependency of another package (e.g. NetworkManager itself commonly depends on it); removing it is out of scope for this audit and any future action here needs its own justification. |

## Services

- No failed systemd units found.
- Active/normal services observed: NetworkManager, SSH, `systemd-timesyncd`, Avahi, Bluetooth,
  `cron`, `dbus`, `getty`, `polkit`, `logind`, `udevd`, `udisks2`, `user@1000`, `wpa_supplicant`.
- SSH is active on port 22, reachable as `michele@home-dns.local`. Not modified during this
  audit; no SSH configuration change is planned until an explicit later hardening task
  requires one.
- Docker: **not installed**. The production architecture stays native (Pi-hole native, Unbound
  native, this application native) — see [../adr/0001-dns-architecture.md](../adr/0001-dns-architecture.md) §2 and [../../deployment/README.md](../../deployment/README.md).

## Security baseline (read-only observation, not a hardening pass)

- No active UFW configuration found.
- No meaningful nftables rules present.
- **This is expected at this stage and is explicitly deferred to Stage C hardening.** This
  audit does not attempt to assess or improve the firewall posture — see CLAUDE.md §47 (change
  safety) and §54 (do not sacrifice stability for premature hardening).
- No passwords, secrets, tokens, private keys, or credentials were recorded anywhere in this
  audit or this document.

## B1 compatibility conclusion

| Area | Conclusion |
|---|---|
| ARM64 compatibility | **OK.** Every backend dependency either is pure Python or ships a prebuilt `manylinux`/aarch64 wheel (verified against `uv.lock`); nothing requires compiling on-device. |
| RAM | **OK for this application's own footprint** (one FastAPI/uvicorn process + SQLite, no cache service). Headroom once Pi-hole FTL and Unbound also run is **not yet measured** — that's a Stage C measurement, not a B1 conclusion. |
| Storage | **OK.** 26 GB free against a design that was already built for a 32 GB card (bounded rollups, size-capped logs, streamed/capped blocklist downloads, tmpfs-ready `paths.tmp_dir` — and `/tmp` is already tmpfs on this Pi). |
| Thermal state | **OK.** ~40.4°C idle is well clear of the Pi 4's throttle point (~80°C). |
| Network | **OK at the interface level** (Gigabit Ethernet up, IPv6 working). DNS-serving behavior (whether clients will actually be pointed at the Pi) depends entirely on the Fastweb Seven, not this Pi — see "Open gates" below. |
| Current DNS ownership | **Intentionally unchanged.** The Pi is not yet doing any DNS work; clients still use the router. This audit did not change that. |
| Production configuration | **Not created.** `config/app/production.yaml` does not exist yet; `production.example.yaml`'s `<<AUDIT:...>>`/`<<REQUIRED:...>>` placeholders remain unfilled. |

## Open gates (ADR 0001 §7)

**Satisfiable from this audit, to be formally recorded in ADR 0001 during B3:**
- **G1** (Raspberry Pi audit): pass criteria met — 64-bit architecture confirmed, storage and
  filesystem healthy, no throttling/overheating, nothing listening on port 53, resource
  baseline recorded above.
- **G2** (resource/performance baseline): idle CPU/RAM/temperature recorded above as a
  comparison point for later measurements (CLAUDE.md §43). Disk-write-rate baseline under
  application load has not been separately measured; not blocking, but worth noting for B3.

**Still fully open, waiting on the Fastweb Seven (B2) — nothing here should be assumed:**
- **G3** — LAN subnet, DHCPv4 options and whether editable, IPv6 RA flags/RDNSS/DHCPv6 DNS and
  whether editable.
- **G4** — whether Fastweb's "DNS protetto"/DNS proxy exists, is on by default, intercepts port
  53, and can be disabled persistently.
- **G5** — how clients actually learn DNS servers over IPv4 and IPv6 on the Box Seven, and
  whether outbound UDP/TCP 53 and 853 reach the Internet unmodified.

**Not yet testable (post-install only):**
- **G6** — MAC-based device group policy correctness over IPv6 (ADR 0001 T4). Requires Pi-hole
  to actually be installed first (Phase 10), so it is a Stage C gate, not a B1/B2 one.

No Fastweb Seven behavior is claimed or assumed anywhere in this document.
