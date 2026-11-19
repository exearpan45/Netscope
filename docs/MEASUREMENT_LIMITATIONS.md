# NETSCOPE Measurement Architecture & Limitations

## 1. System-Wide & Per-Interface Measurements (Exact)
- **Source**: `/proc/net/dev` combined with `ip -j addr show`.
- **Accuracy**: Exact kernel RX/TX byte and packet counters maintained by the Linux networking stack.
- **Interface Classification**:
  - Loopback (`lo`) excluded from internet usage totals by default.
  - Wi-Fi (`wl*`, `wlan*`, `/sys/class/net/<iface>/wireless`), Ethernet (`eth*`, `en*`), VPN (`tun*`, `tap*`, `wg*`, `ppp*`, `tailscale*`, `nordlynx*`), Virtual/Containers (`docker*`, `br-*`, `veth*`, `virbr*`).
- **Rollover / Reboot Resilience**: Deltas are computed against persisted `interface_state` counters; counter resets (on reboot or interface recreate) are detected cleanly without phantom spikes.

## 2. Per-Application & Process Measurements
- **Socket & Process Attribution (Exact)**:
  - Parses `/proc/net/tcp`, `/proc/net/tcp6`, `/proc/net/udp`, `/proc/net/udp6` socket inodes and matches them against `/proc/[PID]/fd` socket symlinks.
  - Groups multi-process apps (e.g., Brave, Firefox, Chrome, VS Code, Nginx, Node.js) cleanly and labels unrecognized sockets under `Unknown Process` or their binary name.
  - Distinguishes LAN/Private endpoints (`RFC1918`, `169.254.0.0/16`, `fc00::/7`, `fe80::/10`) from public Internet endpoints.
- **Per-Process Byte Totals (Capability-Dependent)**:
  - **Tier 1 (`ss -tin` `tcp_info` / eBPF)**: On standard Linux kernels with `NETLINK_SOCK_DIAG` (`CONFIG_INET_TCP_DIAG`) or BTF + `CAP_BPF`, per-socket `bytes_received` and `bytes_acked` (or eBPF kprobes) provide measured per-process byte totals.
  - **Honest Fallback**: When `NETLINK_SOCK_DIAG` or eBPF is blocked by container sandboxes or permissions, NETSCOPE reports `"Not available with current permissions or system capabilities"` for per-process byte totals instead of fabricating or guessing splits from interface counters.

## 3. Browser & Tab Telemetry
- **Source**: Included WebExtension (`netscope/browser_extension/`) + Native Messaging Host (`netscope/native_messaging/netscope_nmh.py`).
- **Accuracy Label**: Explicitly marked **Browser-reported estimate (HTTP headers/payload)** via `webRequest` `Content-Length` headers and request bodies.
- **Limitations**: Browser extensions cannot observe raw TLS record overhead, TCP retransmissions, HTTP/3 QUIC framing, or cached responses lacking `Content-Length`. NETSCOPE never double-counts browser telemetry into system totals.

## 4. Historical Data Recovery
- Scans `/var/lib/vnstat/vnstat.db`, `/var/lib/NetworkManager`, and `/proc/net/dev` + `/proc/uptime` boot counters.
- Explicitly discloses `"Historical per-application usage unavailable before NETSCOPE installation"` unless genuine historical records exist.
