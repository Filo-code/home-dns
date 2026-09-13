# HOME DNS SECURITY, AD BLOCKING, PERFORMANCE & CUSTOM WEB DASHBOARD

## Raspberry Pi 4 — Complete Multi-Agent Project

You are acting as the **lead architect and technical coordinator** for a real home-network infrastructure project.

Your responsibilities cover:

* Network engineering
* DNS engineering
* Linux/Raspberry Pi administration
* Cybersecurity
* DNS filtering
* Performance optimization
* Monitoring
* Automation
* Telegram alerting
* Backend development
* Frontend development
* Database/data architecture
* Testing
* Documentation
* Backup/restore
* Git repository management

The final result must be a **production-quality, maintainable and recoverable home DNS/security platform**, not a temporary experiment.

---

# 0. IMPORTANT — DO NOT ASSUME MY INITIAL ARCHITECTURE IS CORRECT

I initially considered:

* Pi-hole + Unbound
* AdGuard Home
* Technitium DNS Server

You MUST independently evaluate all three.

Do not choose Technitium simply because it was previously suggested.

The architecture must be selected based on the actual requirements below.

---

# 1. MY HARDWARE

## Raspberry Pi

* Raspberry Pi 4
* 4 GB RAM
* 32 GB microSD
* Ethernet connection
* currently intended to run DNS/security services
* NOT a router
* NOT a proxy
* NOT a transparent proxy
* NOT a traffic gateway
* NOT in the normal packet path

The Raspberry Pi should provide DNS services to the LAN.

Future possibility:

* USB 3 SSD

The architecture must make migrating data/logs/configuration from microSD to USB 3 SSD straightforward.

---

# 2. INTERNET CONNECTION

ISP:

**Fastweb — Fastweb Seven Casa**

Connection:

* Fiber
* up to 2.5 Gbit/s
* Fastweb Internet Box Seven

The Fastweb router remains the main:

* router
* gateway
* NAT device
* Internet connection device

The Raspberry Pi should NOT become a network bottleneck.

Desired architecture concept:

```text
                    INTERNET
                       │
                       ▼
              FASTWEB INTERNET BOX
                       │
                       ▼
                      LAN
        ┌──────────────┼──────────────┐
        │              │              │
       PCs            TVs           Xbox
        │              │              │
        └──────────────┼──────────────┘
                       │
                  DNS requests
                       │
                       ▼
                RASPBERRY PI
                  DNS SERVER
                       │
                       ▼
                 DNS resolution
```

---

# 3. HOME NETWORK

Approximately 15–16 devices:

* 3 Smart TVs
* 6 smartphones
* 2–3 iPads
* 3 Windows PCs
* 1 Xbox
* 1 Raspberry Pi
* Fastweb Internet Box Seven
* occasional additional devices

Main Windows PC:

* ASUS ROG STRIX B850-A GAMING WIFI
* 2.5 GbE Ethernet
* Ryzen 7 7800X3D
* Radeon RX 7800 XT

The architecture should be compatible with a 2.5 Gbit/s LAN/Internet environment.

---

# 4. FIRST TASK — ARCHITECTURE EVALUATION

Before implementation, compare:

## A — Pi-hole + Unbound

## B — AdGuard Home

## C — Technitium DNS Server

Evaluate all three against THIS project.

---

# 5. ARCHITECTURE DECISION MATRIX

Create a weighted decision matrix.

Evaluate:

### DNS

* recursive DNS
* forwarding DNS
* DNSSEC
* cache
* persistent cache
* prefetch
* serve-stale
* negative caching
* IPv4
* IPv6
* DoH
* DoT
* DoQ
* local DNS
* reverse DNS
* DNS rebinding protection

### Filtering

* advertisements
* trackers
* malware
* phishing
* malvertising
* gambling
* adult content
* telemetry
* custom lists
* regex
* allowlists
* denylists
* per-device rules
* per-group rules

### API

Evaluate:

* API completeness
* API documentation
* clients API
* query API
* statistics API
* blocking API
* configuration API
* automation
* monitoring
* scripting

### Custom Web App

This is one of the MOST IMPORTANT criteria.

I want my own modern web dashboard.

Evaluate:

* API quality
* real-time information
* historical statistics
* device management
* custom names
* policy management
* security data
* performance data
* charts
* alerts
* authentication
* future extensibility

### Performance

Evaluate:

* CPU
* RAM
* DNS latency
* throughput
* cache efficiency
* disk writes
* microSD wear
* SSD support
* 24/7 operation

### Security

Evaluate:

* DNSSEC
* DNS hijacking
* DNS bypass
* encrypted DNS
* DoH
* DoT
* DoQ
* browser Secure DNS
* Windows Secure DNS
* Android Private DNS
* iOS/iPadOS
* Xbox

### Compatibility

Evaluate:

* Windows
* Android
* iOS
* iPadOS
* Smart TVs
* Xbox
* Netflix
* YouTube
* Prime Video
* Disney+
* DAZN
* Twitch
* Steam
* Microsoft
* Apple
* Google
* Amazon
* social networks

### Maintenance

Evaluate:

* updates
* rollback
* backups
* blocklist updates
* monitoring
* cleanup
* recovery

---

# 6. FINAL ARCHITECTURE RANKING

After the analysis, provide:

1. Best overall
2. Best customization
3. Best custom web dashboard
4. Best API
5. Best performance
6. Best stability
7. Best security
8. Best Smart TV compatibility
9. Best Xbox compatibility
10. Best simplicity
11. Best long-term extensibility

Then make ONE final recommendation.

If the recommendation differs from Technitium, use the better solution.

---

# 7. CURRENT OFFICIAL DOCUMENTATION

Before making implementation decisions, verify the current 2026 official documentation for:

* selected DNS software
* Raspberry Pi OS
* relevant APIs
* router/network capabilities
* relevant security mechanisms

Prefer official documentation over random tutorials.

If current documentation contradicts assumptions in this prompt, trust the current official documentation and explain the change.

---

# 8. PROJECT STRUCTURE — CREATE IT PROPERLY

I do NOT want a messy collection of scripts.

Create a professional project structure.

At minimum:

```text
home-dns/
│
├── README.md
├── CHANGELOG.md
├── LICENSE
├── .gitignore
├── .env.example
│
├── docs/
│   ├── architecture.md
│   ├── installation.md
│   ├── networking.md
│   ├── dns.md
│   ├── ipv4.md
│   ├── ipv6.md
│   ├── dns-bypass.md
│   ├── blocklists.md
│   ├── protected-domains.md
│   ├── devices.md
│   ├── policies.md
│   ├── smart-tv.md
│   ├── xbox.md
│   ├── telegram-alerts.md
│   ├── monitoring.md
│   ├── maintenance.md
│   ├── storage.md
│   ├── backups.md
│   ├── restore.md
│   ├── security.md
│   ├── troubleshooting.md
│   └── development.md
│
├── config/
│   ├── dns/
│   ├── groups/
│   ├── policies/
│   ├── protected-domains/
│   ├── telegram/
│   ├── monitoring/
│   └── storage/
│
├── lists/
│   ├── core/
│   ├── italian/
│   ├── malware/
│   ├── phishing/
│   ├── telemetry/
│   ├── gambling/
│   └── adult/
│
├── scripts/
│   ├── audit/
│   ├── install/
│   ├── setup/
│   ├── update/
│   ├── blocklists/
│   ├── monitoring/
│   ├── maintenance/
│   ├── backup/
│   ├── restore/
│   └── tests/
│
├── dashboard/
│   ├── backend/
│   ├── frontend/
│   ├── shared/
│   └── README.md
│
├── tests/
│   ├── dns/
│   ├── security/
│   ├── compatibility/
│   ├── blocklists/
│   ├── api/
│   └── dashboard/
│
├── deployment/
│   ├── systemd/
│   ├── docker/
│   └── nginx/
│
└── data/
    ├── README.md
    └── .gitkeep
```

Adapt the structure if the selected architecture requires something different.

---

# 9. IMPORTANT — DOCUMENT EVERYTHING

Every important component must have documentation.

Documentation must explain:

* what it does
* why it exists
* dependencies
* configuration
* installation
* operation
* troubleshooting
* recovery
* rollback
* security implications

The goal is that another technically competent person can maintain the system without needing the original conversation.

---

# 10. MULTI-AGENT DEVELOPMENT

Use a **multi-agent workflow** where appropriate.

Do NOT have multiple agents blindly modifying the same files at the same time.

You are the **Lead Agent / Architect**.

Use specialized agents for independent areas.

Suggested roles:

### Agent 1 — Network Architect

Responsible for:

* Raspberry Pi network audit
* Fastweb router analysis
* LAN topology
* IPv4
* IPv6
* DHCP
* DNS advertisement
* DNS bypass
* network security

### Agent 2 — DNS Specialist

Responsible for:

* Pi-hole + Unbound analysis
* AdGuard Home analysis
* Technitium analysis
* DNS architecture
* caching
* DNSSEC
* recursive resolution
* filtering
* performance

### Agent 3 — Security Specialist

Responsible for:

* malware
* phishing
* malvertising
* DNS bypass
* protected-domain system
* security policies
* blocklist validation
* threat model

### Agent 4 — Backend Engineer

Responsible for:

* DNS API integration
* backend architecture
* data normalization
* historical metrics
* device management
* policy management
* alert engine

### Agent 5 — Frontend Engineer

Responsible for:

* dashboard UI
* responsive design
* charts
* devices page
* security page
* performance page
* responsive PC/iPad/mobile layouts

### Agent 6 — Monitoring / Automation Engineer

Responsible for:

* health checks
* watchdog
* maintenance
* storage guard
* blocklist pipeline
* backups
* recovery
* scheduled jobs

### Agent 7 — Testing Engineer

Responsible for:

* DNS tests
* security tests
* API tests
* compatibility tests
* dashboard tests
* regression tests
* performance tests

### Agent 8 — Documentation Engineer

Responsible for:

* README
* architecture docs
* installation
* troubleshooting
* backup/restore
* operational procedures
* developer documentation

---

# 11. MULTI-AGENT RULES

Agents must:

* communicate findings clearly
* avoid duplicate work
* avoid conflicting changes
* work in isolated branches/worktrees when appropriate
* commit meaningful changes
* report assumptions
* report blockers
* report tests performed
* never silently change architecture

The Lead Agent decides when changes are merged.

Before merging an agent's work:

1. review
2. test
3. verify compatibility
4. check security
5. check documentation
6. merge

Do not merge blindly.

---

# 12. PARALLELIZATION

Parallelize only genuinely independent tasks.

Good examples:

* documentation research
* architecture comparisons
* blocklist research
* frontend design research
* security analysis

Do NOT parallelize tasks that modify the same configuration or depend on the result of another task.

Example:

Do NOT simultaneously have three agents modify the final DNS configuration.

---

# 13. FIRST PHASE — AUDIT ONLY

The first real implementation phase is AUDIT ONLY.

Do NOT:

* install DNS software
* change DNS
* change DHCP
* change IPv6
* change firewall
* change routing
* install blocklists
* deploy dashboard
* modify Fastweb router
* modify network configuration

during the initial audit.

---

# 14. RASPBERRY PI AUDIT

Inspect:

* OS
* OS version
* kernel
* architecture
* CPU
* RAM
* storage
* filesystem
* microSD
* temperature
* uptime
* IP addresses
* gateway
* DNS
* IPv4
* IPv6
* DHCP
* interfaces
* Ethernet speed
* Wi-Fi
* services
* listening ports
* firewall
* Docker
* existing DNS services
* disk usage
* logs
* cron
* systemd
* failed services
* errors
* installed packages
* existing repositories
* existing applications

Check for:

* filesystem errors
* storage problems
* excessive logging
* high disk usage
* overheating
* unstable services

Do not modify anything.

---

# 15. NETWORK AUDIT

Determine:

* LAN subnet
* DHCP range
* current DNS
* gateway
* IPv4
* IPv6
* Router Advertisement
* DHCPv6
* DNS advertisement
* Fastweb router capabilities
* custom DNS support
* DNS interception/redirection
* IPv6 DNS configuration
* DNS bypass possibilities
* encrypted DNS bypass possibilities
* Ethernet link speed

Document limitations.

---

# 16. STORAGE STRATEGY

The Raspberry Pi currently has:

**32 GB microSD**

Design for minimal unnecessary writes.

Implement:

* log rotation
* query retention
* cleanup
* compression where appropriate
* storage monitoring
* automatic cleanup

Thresholds:

### <70%

Healthy

### 70–80%

Warning

### 80–90%

Automatic cleanup

### >90%

Emergency cleanup + Telegram alert

The system must never allow logs to grow indefinitely.

Target DNS query retention:

approximately 30 days.

Adjust if technically justified.

---

# 17. FUTURE SSD MIGRATION

Design storage paths logically.

For example:

```text
/opt/home-dns/
    config/
    data/
    logs/
    backups/
```

or another appropriate architecture.

The important requirement is:

**future migration from microSD to USB 3 SSD should not require rewriting the application.**

Document the migration procedure.

---

# 18. DNS FILTERING

Start with a small number of high-quality lists.

Initial core:

* HaGeZi Multi PRO
* HaGeZi TIF Mini

Verify current availability and compatibility first.

Then consider carefully selected:

* Italian advertising
* Italian trackers
* malware
* phishing
* gambling
* adult
* telemetry

Avoid unnecessary duplication.

Prioritize:

**low false positives + low overhead + high protection.**

---

# 19. PROTECTED DOMAIN TRIPWIRE

Create a protected-domain database.

Include:

### Italian

* Poste Italiane
* SPID
* PagoPA
* Agenzia delle Entrate
* major banks
* payment infrastructure

### Technology

* Google
* Microsoft
* Apple
* Amazon
* Steam
* Xbox
* Netflix
* Prime Video
* Disney+
* YouTube
* Twitch

### Infrastructure

* major CDNs
* authentication services
* OS updates
* certificate infrastructure
* critical cloud infrastructure
* DNS infrastructure

Before every blocklist deployment:

```text
Download
↓
Validate
↓
Normalize
↓
Deduplicate
↓
Protected-domain scan
↓
Syntax validation
↓
Sanity check
↓
Test
↓
Deploy
↓
Health check
```

If a protected domain is detected:

**ABORT DEPLOYMENT.**

Keep the previous working list.

Send Telegram warning/critical alert.

---

# 20. DEVICE GROUPS

Implement:

```text
DEFAULT
PC
GAMING
MOBILE
SMART-TV
XBOX
```

You may improve this design.

The dashboard should allow changing device groups.

---

# 21. DEVICE IDENTIFICATION

Use:

* IP
* MAC
* hostname
* DHCP information
* DNS client information
* reliable identifiers

Allow custom device names.

Example:

* Michele PC
* Living Room TV
* Bedroom TV
* Xbox
* iPhone
* iPad

Track:

* first seen
* last seen
* queries
* blocked
* allowed
* top domains
* policy group

---

# 22. SMART TV POLICY

Conservative.

Block:

* obvious ads
* malware
* obvious trackers
* dangerous domains

Be careful with telemetry.

Never unnecessarily break:

* Netflix
* YouTube
* Prime Video
* Disney+
* DAZN
* DRM
* casting
* app stores
* updates
* authentication
* CDNs

---

# 23. XBOX POLICY

Conservative.

Preserve:

* Xbox Live
* Microsoft Account
* multiplayer
* matchmaking
* Game Pass
* Store
* downloads
* updates
* parties
* voice
* authentication
* Microsoft infrastructure

---

# 24. SOCIAL NETWORKS

Keep fully functional:

* Instagram
* Facebook
* TikTok
* X
* Reddit
* Telegram
* WhatsApp
* Discord
* Snapchat

Only block safe advertising/tracking/malicious infrastructure.

---

# 25. YOUTUBE

Do NOT attempt aggressive DNS-level YouTube ad blocking.

Do NOT block:

* googlevideo.com
* YouTube video infrastructure
* Google CDN infrastructure
* essential APIs

Prioritize functionality.

---

# 26. TWITCH

Do not block streaming infrastructure.

Preserve:

* video
* streams
* chat
* authentication
* subscriptions
* CDN

---

# 27. IPV6

Do NOT simply disable IPv6.

Determine:

* whether Fastweb provides IPv6
* whether the router advertises DNS over IPv6
* whether clients can bypass the Raspberry Pi
* whether the selected DNS solution supports IPv6
* how to prevent DNS leakage while preserving IPv6

Document everything.

---

# 28. DNS BYPASS

Analyze:

* manual DNS
* 1.1.1.1
* 8.8.8.8
* 9.9.9.9
* DoH
* DoT
* DoQ
* browser Secure DNS
* Windows Secure DNS
* Android Private DNS
* iOS/iPadOS encrypted DNS
* Xbox DNS

Do not break encrypted DNS blindly.

Use router-level mitigation only if technically supported and safe.

No DPI unless explicitly approved.

---

# 29. TELEGRAM ALERTING

Telegram notifications are mandatory.

Alert on:

### CRITICAL

* DNS down
* DNS unavailable
* critical DNSSEC failure
* storage >90%
* filesystem nearly full
* dangerous temperature
* backup failure
* configuration failure
* health check failure
* suspected DNS bypass
* failed deployment
* failed update
* rollback
* protected-domain tripwire failure

### WARNING

* storage >70%
* storage >80%
* abnormal DNS latency
* abnormal query growth
* high CPU
* high RAM
* unexpected service restart
* blocklist update failure
* suspicious blocklist
* protected-domain warning
* missing backup
* IPv6 bypass

### INFO

Optionally:

* backup completed
* update completed
* blocklist updated
* reboot
* service recovered

---

# 30. TELEGRAM ANTI-SPAM

Implement:

* cooldown
* rate limiting
* deduplication
* incident state tracking
* recovery notifications

Example:

```text
DNS DOWN
→ Telegram alert

DNS remains down
→ no repeated spam

DNS RECOVERED
→ recovery alert
```

---

# 31. SECRET MANAGEMENT

NEVER commit:

* Telegram token
* passwords
* API keys
* SSH keys
* session tokens

Use:

* environment variables
* protected secret files
* systemd EnvironmentFile
* appropriate filesystem permissions

Create:

```text
.env.example
```

Never commit:

```text
.env
```

---

# 32. MONITORING

Monitor:

* DNS service
* DNS response
* DNSSEC
* DNS latency
* Internet
* LAN DNS
* IPv4
* IPv6
* CPU
* RAM
* temperature
* storage
* uptime
* system errors
* backups
* blocklist updates
* configuration integrity

Recovery process:

```text
Detect
↓
Retry
↓
Backoff
↓
Recover if safe
↓
Verify
↓
Notify
```

No infinite restart loops.

---

# 33. BACKUPS

Implement:

* daily backups
* weekly backups
* configuration backup
* policies
* device mappings
* dashboard configuration
* blocklist configuration

Avoid huge query-history backups.

Test restoration.

A backup is NOT considered valid until restore has been tested.

---

# 34. SAFE UPDATE PROCESS

Every update:

```text
Check
↓
Backup
↓
Update
↓
Health check
↓
DNS test
↓
Filtering test
↓
Success
```

Failure:

```text
Rollback
↓
Health check
↓
Telegram alert
```

---

# 35. CUSTOM DASHBOARD

Build a completely custom dashboard.

LAN-only.

Never expose publicly.

Responsive:

* desktop
* iPad
* mobile

Modern UI.

Fast.

Clear.

---

# 36. DASHBOARD — OVERVIEW

Show:

* DNS status
* DNS latency
* queries/sec
* total queries
* blocked
* allowed
* block percentage
* cache hit ratio
* CPU
* RAM
* temperature
* storage
* uptime
* last backup
* last blocklist update
* security status

---

# 37. DASHBOARD — DEVICES

Show:

* custom name
* IP
* MAC
* hostname
* type
* group
* first seen
* last seen
* total queries
* blocked
* allowed
* block percentage
* top requested domains
* top blocked domains
* recent activity

Allow:

* rename
* assign group
* assign policy

---

# 38. DASHBOARD — SECURITY

Show:

* malware
* phishing
* advertising
* trackers
* gambling
* adult
* telemetry
* suspicious activity
* DNS bypass
* protected-domain warnings
* DNSSEC
* blocklist health

---

# 39. DASHBOARD — PERFORMANCE

Show:

* average DNS latency
* p50
* p95
* cache hit ratio
* queries/sec
* CPU
* RAM
* temperature
* storage
* uptime
* restarts
* errors

---

# 40. API ARCHITECTURE

Prefer:

```text
DNS SERVER
     ↓
OFFICIAL API
     ↓
BACKEND
     ↓
DATA / METRICS
     ↓
FRONTEND
```

Do NOT directly manipulate internal databases unless absolutely necessary.

The backend should handle:

* authentication
* API integration
* normalization
* device names
* policies
* historical metrics
* alert engine
* security statistics

---

# 41. GIT

Use Git from the beginning.

Suggested commits:

```text
initial-project
raspberry-audit
network-audit
architecture-selected
dns-server-installed
dns-configured
ipv6-configured
core-lists
italian-filter
device-policies
telegram-alerts
maintenance-system
dashboard-foundation
dashboard-devices
dashboard-security
dashboard-performance
final-network-config
```

Use meaningful commits only.

---

# 42. TESTING

Create automated tests where appropriate.

Test:

### DNS

* normal resolution
* DNSSEC
* IPv4
* IPv6
* cache
* blocked domains
* allowed domains
* protected domains
* local DNS

### Security

* malware
* phishing
* tracker
* ad
* gambling
* adult

Use safe test domains and documented test mechanisms.

Do not intentionally visit dangerous websites.

### Compatibility

* Windows
* Android
* iOS
* iPadOS
* Smart TV
* Xbox
* Netflix
* YouTube
* Prime Video
* Disney+
* DAZN
* Twitch
* Steam
* Microsoft
* Apple
* Google
* Amazon
* social networks

---

# 43. PERFORMANCE TESTING

Measure:

* DNS latency
* cache hit rate
* queries/sec
* CPU
* RAM
* storage I/O
* temperature
* uptime

Test under realistic home-network load.

Do not optimize prematurely.

Measure before and after major changes.

---

# 44. DOCUMENTATION REQUIREMENTS

The documentation must include practical instructions.

For example:

```text
How to install
How to update
How to restart
How to check DNS
How to check logs
How to restore backup
How to recover from failure
How to add a device
How to rename a device
How to change a policy
How to add a blocklist
How to remove a blocklist
How to test DNSSEC
How to diagnose DNS bypass
How to migrate to SSD
How to configure Telegram
How to troubleshoot Smart TV
How to troubleshoot Xbox
How to rollback
```

Include actual commands where appropriate.

Do not assume the user knows Linux administration.

---

# 45. README

Create a professional README containing:

* project purpose
* architecture
* requirements
* installation
* configuration
* dashboard
* Telegram
* maintenance
* backups
* troubleshooting
* security
* development
* contribution/workflow

---

# 46. DEVELOPMENT WORKFLOW

I work primarily from:

* VS Code
* SSH
* Raspberry Pi
* Windows PC
* macOS when useful

Use VS Code Remote SSH where appropriate.

Do not give me hundreds of commands at once.

Work incrementally.

For every important step:

1. explain what we are doing
2. provide a small number of commands
3. wait for output
4. analyze output
5. continue

Never assume command output.

---

# 47. CHANGE SAFETY

Before modifying:

* DNS
* DHCP
* IPv6
* firewall
* routing
* router
* network interfaces

explain:

* what will change
* why
* risks
* how to undo it

Avoid destructive commands.

Never make irreversible changes without approval.

---

# 48. PHASED IMPLEMENTATION

Follow:

## Phase 1

Raspberry Pi audit

## Phase 2

Network audit

## Phase 3

Architecture comparison

## Phase 4

Architecture approval

## Phase 5

DNS installation

## Phase 6

Base DNS

## Phase 7

DNS testing

## Phase 8

Core filtering

## Phase 9

Italian filtering

## Phase 10

Device policies

## Phase 11

IPv6 + DNS bypass

## Phase 12

Maintenance

## Phase 13

Telegram

## Phase 14

Dashboard

## Phase 15

Testing

## Phase 16

Backup/restore

## Phase 17

Documentation

---

# 49. IMPORTANT — PROJECT SCAFFOLDING

After the architecture has been evaluated and before major implementation begins, create the complete project structure.

Create:

* directories
* README
* documentation placeholders
* configuration structure
* scripts structure
* dashboard structure
* tests structure
* deployment structure
* .gitignore
* .env.example
* initial configuration templates

Do NOT fill configuration with unsafe assumptions.

Do NOT put secrets into templates.

Do NOT install the production DNS service merely because the directory structure has been created.

The repository should be clean and understandable from the beginning.

---

# 50. AGENT HANDOFF FORMAT

When delegating work to another agent, provide:

```text
TASK
OBJECTIVE
CONTEXT
FILES/DIRECTORIES
CONSTRAINTS
DEPENDENCIES
EXPECTED OUTPUT
TESTS REQUIRED
DO NOT MODIFY
```

The agent must return:

```text
SUMMARY
CHANGES
FILES
TESTS
RESULTS
ASSUMPTIONS
RISKS
FOLLOW-UP
```

---

# 51. LEAD AGENT RESPONSIBILITIES

You are responsible for maintaining a coherent architecture.

Before accepting agent work, verify:

* no contradictions
* no duplicated systems
* no unnecessary dependencies
* security
* performance
* compatibility
* documentation
* tests
* rollback capability

If two agents propose conflicting solutions:

1. stop
2. compare
3. explain trade-offs
4. choose one
5. document the decision

Never silently combine incompatible architectures.

---

# 52. ARCHITECTURE DECISION RECORDS

For important decisions, create ADRs.

Example:

```text
docs/adr/
├── 0001-dns-architecture.md
├── 0002-storage-strategy.md
├── 0003-ipv6-strategy.md
├── 0004-blocklist-strategy.md
├── 0005-dashboard-architecture.md
└── 0006-telegram-alerting.md
```

Each ADR should explain:

* decision
* alternatives
* reasoning
* consequences

---

# 53. FINAL QUALITY STANDARD

The finished system should have:

* stable DNS
* fast DNS
* secure DNS
* high-quality filtering
* low false positives
* Smart TV compatibility
* Xbox compatibility
* social-media compatibility
* IPv4
* IPv6 where appropriate
* DNS bypass awareness
* automated blocklist validation
* protected-domain safety
* automatic maintenance
* storage protection
* backups
* tested restore
* Telegram alerts
* health monitoring
* custom dashboard
* device identification
* policy groups
* security statistics
* performance statistics
* documentation
* Git history
* rollback capability

---

# 54. MOST IMPORTANT PRIORITIES

Prioritize in this order:

1. Stability
2. DNS performance
3. Compatibility
4. Security
5. Filtering quality
6. Observability
7. Automation
8. Customization

Do NOT sacrifice stability merely to add features.

Avoid unnecessary components.

Avoid unnecessary disk writes.

Avoid unnecessary network complexity.

Avoid unnecessary containers/services.

---

# 55. FINAL RULE

Think like a senior engineer responsible for keeping this network running 24/7.

Do not blindly execute instructions.

If there is a better solution, explain it.

If a requirement is technically impossible or unreliable, say so.

If DNS filtering cannot safely achieve something, do not pretend it can.

If a blocklist is dangerous, reject it.

If a configuration could break Smart TVs, Xbox or normal Internet access, test and document it.

If an update can cause downtime, design rollback first.

If storage could fill up, prevent it automatically.

If something important fails, notify me through Telegram.

If something recovers, notify me.

The system must be designed for **real-world reliability, maintainability and future expansion**.

---

# START NOW

Do NOT install anything.

Do NOT modify networking.

Do NOT modify DNS.

Do NOT modify DHCP.

Do NOT modify IPv6.

Do NOT modify the router.

Do NOT deploy blocklists.

Do NOT deploy the dashboard.

First:

### STEP 1

Perform the Raspberry Pi audit.

### STEP 2

Perform the network audit.

### STEP 3

Compare Pi-hole + Unbound vs AdGuard Home vs Technitium.

### STEP 4

Create the architecture decision matrix.

### STEP 5

Recommend the best architecture.

### STEP 6

Present the proposed final architecture.

### STEP 7

Create the initial Git/project folder structure and documentation scaffold.

Then STOP and wait for approval before making production/network changes.

Do not skip the audit.

Do not skip the architecture comparison.

Do not assume the answer in advance.
