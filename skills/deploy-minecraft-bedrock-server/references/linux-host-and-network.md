# Linux host and network assessment

> **Validation provenance:** The checklist and sizing guidance are conservative operational guidance, not a record that every check was run on the Tencent Cloud host. The audit and redaction scripts are synthetic/local-tested. RakNet public reachability and representative-player latency remain host-specific measurements.

## Read-only discovery

**Source:** Operational guidance. Execute and record these checks on the actual target before making host-specific claims.

Collect before recommending or installing:

- `/etc/os-release`, kernel, architecture, virtualization and provider image.
- Logical CPUs, model, clock visibility and steal time.
- Total/available RAM, swap size/use and OOM history.
- Filesystem type, total/free space, inode use and expected backup headroom.
- Load average, per-process CPU/RSS, current proxies, databases and other latency-sensitive services.
- Listening TCP/UDP ports, guest firewall, cloud security group and provider traffic/bandwidth limits.
- Public IPv4/IPv6 from the cloud console or an authorized external lookup.
- Latency and packet loss from representative player regions when possible.

Run `scripts/audit-linux-minecraft-host.sh`. It does not install packages, change state, or print full process arguments by default. Its CPU snapshot uses `vmstat`; it deliberately avoids `top`, whose remembered display mode can expose full command lines on some hosts. Use `--include-command-lines` only when explicitly needed; redaction is best-effort, so keep that output private. Supplement it with provider-console checks because a guest cannot reliably prove whether an upstream security group permits UDP.

## Sizing heuristics

**Source:** Operational guidance informed by the small Bedrock deployment; these are starting points, not production guarantees for every VPS.

Treat these as starting points, not guarantees:

- CPU single-thread performance and stable scheduling matter more than a large vCPU label.
- Two to four Bedrock players with a modest world and light add-ons commonly fit in 2 vCPU/4 GiB more comfortably than 2 GiB. Leave capacity for the OS and existing services.
- Swap prevents abrupt OOM termination but does not substitute for RAM. Sustained swap-in/out causes severe tick and latency spikes; zero swap is acceptable only with ample memory headroom and monitoring.
- Keep at least two complete world copies plus upgrade/rollback space. A 400–500 MB world can use substantially more disk during LevelDB compaction and backups.
- A 3 Mbps capped link is usually enough for ordinary gameplay for a few players, but initial resource-pack downloads, backups and other VPS traffic can saturate it. Verify provider definitions for peak bandwidth and monthly transfer.
- Choose the region by measured or estimated compromise among all players, not only the purchaser. For players spread across central, south and southwest mainland China, compare Guangzhou and Shanghai routes from each ISP; do not infer from geographic distance alone.

## Network verification

**Source:** Official protocol defaults plus operational guidance. The bundled probe has localhost loopback coverage; a public result is valid only for the tested host and path.

- BDS normally uses UDP 19132 for IPv4 and UDP 19133 for IPv6.
- Verify three layers separately: process listening, guest firewall, cloud security group.
- Test BDS with `scripts/probe-bedrock.py HOST PORT`; a RakNet pong proves public UDP reachability and exposes protocol version, online count and MOTD.
- Never conclude that a port can be opened merely because nothing currently listens on it.

## Coexistence rules

**Source:** Operational safety guidance. Preserving the existing proxy was a real project constraint, but every rule below was not independently exercised as a failure test.

- Identify the proxy service unit, executable, ports, CPU and memory before deployment.
- Avoid blanket firewall replacement commands. Add only narrow rules after showing the exact change.
- Use a separate service user and install directory.
- Avoid rebooting. If a kernel/provider action truly requires one, stop and request explicit authorization.
- Measure post-deployment memory and CPU with representative player load, not only at idle.
