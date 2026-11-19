"""Real Linux kernel & /proc network monitoring engine for NETSCOPE.

Reads:
- /proc/net/dev for exact kernel interface RX/TX byte & packet counters
- `ip -j addr show` & /sys/class/net (when present) for interface types, IPs, MAC, MTU, state
- /proc/net/tcp, /proc/net/tcp6, /proc/net/udp, /proc/net/udp6 for active sockets
- /proc/[PID]/fd, /proc/[PID]/cmdline, /proc/[PID]/comm, /proc/[PID]/exe, /proc/[PID]/status
- `ss -tinap` for kernel tcp_info bytes_received / bytes_acked when netlink SOCK_DIAG is supported
"""

from __future__ import annotations

import ipaddress
import json
import os
import pwd
import re
import shutil
import socket
import struct
import subprocess
from dataclasses import dataclass
from typing import Any

TCP_STATES = {
    "01": "ESTABLISHED",
    "02": "SYN_SENT",
    "03": "SYN_RECV",
    "04": "FIN_WAIT1",
    "05": "FIN_WAIT2",
    "06": "TIME_WAIT",
    "07": "CLOSE",
    "08": "CLOSE_WAIT",
    "09": "LAST_ACK",
    "0A": "LISTEN",
    "0B": "CLOSING",
    "0C": "NEW_SYN_RECV",
}

APP_CATALOG: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"(brave-browser|brave)", re.I), "brave", "Brave Browser"),
    (re.compile(r"(firefox|firefox-esr|navigator)", re.I), "firefox", "Firefox"),
    (re.compile(r"(google-chrome|chrome)", re.I), "google-chrome", "Google Chrome"),
    (re.compile(r"(chromium|chromium-browser)", re.I), "chromium", "Chromium"),
    (re.compile(r"(msedge|microsoft-edge)", re.I), "msedge", "Microsoft Edge"),
    (re.compile(r"(code|vscode|codium)", re.I), "vscode", "VS Code"),
    (re.compile(r"(discord)", re.I), "discord", "Discord"),
    (re.compile(r"(telegram|telegram-desktop)", re.I), "telegram", "Telegram"),
    (re.compile(r"(steam|steamwebhelper)", re.I), "steam", "Steam"),
    (re.compile(r"(apt|apt-get|dpkg|unattended-upgr|packagekitd|snapd|flatpak)", re.I), "system-updates", "System Update Services"),
    (re.compile(r"(nginx)", re.I), "nginx", "Nginx"),
    (re.compile(r"(node|nodejs|tsx|vite|npm)", re.I), "nodejs", "Node.js Runtime"),
    (re.compile(r"(python3?|uvicorn|gunicorn)", re.I), "python", "Python Runtime"),
    (re.compile(r"(systemd-resolve|systemd-network|NetworkManager|wpa_supplicant|dhclient|openvpn|wg-quick|tailscaled)", re.I), "system-network", "System Network Services"),
    (re.compile(r"(curl|wget|aria2c|rsync|scp|ssh|git)", re.I), "cli-transfer", "CLI Network Tools"),
    (re.compile(r"(control-plane)", re.I), "control-plane", "Host Control Plane"),
]


@dataclass
class InterfaceSnapshot:
    iface: str
    iface_type: str
    rx_bytes: int
    tx_bytes: int
    rx_packets: int
    tx_packets: int
    status: str
    ip_addresses: list[dict[str, Any]]
    mac_address: str
    mtu: int
    is_loopback: bool
    is_vpn: bool


def classify_interface_type(iface: str, link_type: str = "") -> str:
    low = iface.lower()
    if low == "lo" or link_type == "loopback":
        return "loopback"
    if (
        low.startswith(("wl", "wlan", "wlp", "wifi", "ath", "ra"))
        or os.path.exists(f"/sys/class/net/{iface}/wireless")
    ):
        return "wifi"
    if low.startswith(("tun", "tap", "wg", "ppp", "nordlynx", "tailscale", "proton", "mullvad", "vpn")):
        return "vpn"
    if low.startswith(("docker", "br-", "veth", "virbr", "cni", "podman", "lxc", "vboxnet", "vmnet")):
        return "virtual"
    if low.startswith(("en", "eth", "em", "p")) or link_type == "ether":
        return "ethernet"
    return "other"


def is_lan_or_local_ip(ip_str: str) -> bool:
    if not ip_str or ip_str in ("0.0.0.0", "::", "*"):
        return True
    try:
        # Handle IPv4-mapped IPv6 like ::ffff:127.0.0.1
        addr = ipaddress.ip_address(ip_str)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        return bool(
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        )
    except ValueError:
        return False


def read_ip_metadata() -> dict[str, dict[str, Any]]:
    """Query `ip -j addr show` if available for real interface status, IPs, MAC, MTU."""
    meta: dict[str, dict[str, Any]] = {}
    ip_bin = shutil.which("ip")
    if not ip_bin:
        return meta
    try:
        res = subprocess.run(
            [ip_bin, "-j", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return meta
        items = json.loads(res.stdout)
        for item in items:
            name = item.get("ifname")
            if not name:
                continue
            flags = item.get("flags", [])
            oper = item.get("operstate", "").upper()
            up = ("UP" in flags and "LOWER_UP" in flags) or oper == "UP"
            addrs = []
            for a in item.get("addr_info", []):
                addrs.append(
                    {
                        "family": a.get("family", ""),
                        "local": a.get("local", ""),
                        "prefixlen": a.get("prefixlen", 0),
                        "scope": a.get("scope", ""),
                    }
                )
            meta[name] = {
                "link_type": item.get("link_type", ""),
                "status": "up" if up else ("administratively_up" if "UP" in flags else "down"),
                "ip_addresses": addrs,
                "mac_address": item.get("address", ""),
                "mtu": int(item.get("mtu", 0) or 0),
            }
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return meta


def read_proc_net_dev() -> list[InterfaceSnapshot]:
    """Read exact kernel interface counters from /proc/net/dev."""
    ip_meta = read_ip_metadata()
    snapshots: list[InterfaceSnapshot] = []
    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return snapshots

    for line in lines[2:]:
        if ":" not in line:
            continue
        iface_part, stats_part = line.split(":", 1)
        iface = iface_part.strip()
        fields = stats_part.split()
        if len(fields) < 16:
            continue
        rx_bytes = int(fields[0])
        rx_packets = int(fields[1])
        tx_bytes = int(fields[8])
        tx_packets = int(fields[9])

        m = ip_meta.get(iface, {})
        link_type = m.get("link_type", "")
        iface_type = classify_interface_type(iface, link_type)
        status = m.get("status", "unknown")
        if status == "unknown" and os.path.exists(f"/sys/class/net/{iface}/operstate"):
            try:
                with open(f"/sys/class/net/{iface}/operstate", "r", encoding="utf-8") as sfh:
                    status = sfh.read().strip().lower()
            except OSError:
                pass

        snapshots.append(
            InterfaceSnapshot(
                iface=iface,
                iface_type=iface_type,
                rx_bytes=rx_bytes,
                tx_bytes=tx_bytes,
                rx_packets=rx_packets,
                tx_packets=tx_packets,
                status=status,
                ip_addresses=m.get("ip_addresses", []),
                mac_address=m.get("mac_address", ""),
                mtu=m.get("mtu", 0),
                is_loopback=(iface_type == "loopback"),
                is_vpn=(iface_type == "vpn"),
            )
        )
    return snapshots


def _decode_proc_ip_port(hex_addr: str, is_v6: bool) -> tuple[str, int]:
    ip_hex, port_hex = hex_addr.split(":")
    port = int(port_hex, 16)
    if not is_v6:
        raw = bytes.fromhex(ip_hex)
        # /proc/net/tcp stores IPv4 in host/little-endian 32-bit word on x86_64
        ip_int = struct.unpack("<I", raw)[0]
        ip_str = socket.inet_ntoa(struct.pack("!I", ip_int))
        return ip_str, port
    # IPv6 in /proc/net/tcp6 is 4 x 32-bit little-endian words
    raw = bytes.fromhex(ip_hex)
    words = struct.unpack("<4I", raw)
    packed = struct.pack("!4I", *words)
    ip_str = socket.inet_ntop(socket.AF_INET6, packed)
    return ip_str, port


def _parse_proc_socket_table(path: str, proto: str, is_v6: bool) -> dict[str, dict[str, Any]]:
    """Return mapping of socket_inode -> socket details."""
    sockets: dict[str, dict[str, Any]] = {}
    if not os.path.exists(path):
        return sockets
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return sockets

    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 10:
            continue
        local_ip, local_port = _decode_proc_ip_port(parts[1], is_v6)
        remote_ip, remote_port = _decode_proc_ip_port(parts[2], is_v6)
        st_hex = parts[3].upper()
        state = TCP_STATES.get(st_hex, st_hex) if proto.startswith("tcp") else ("ESTABLISHED" if remote_port > 0 else "UNCONN")
        uid = int(parts[7]) if parts[7].isdigit() else -1
        inode = parts[9]
        if inode == "0":
            continue
        sockets[inode] = {
            "proto": proto,
            "local_ip": local_ip,
            "local_port": local_port,
            "remote_ip": remote_ip,
            "remote_port": remote_port,
            "state": state,
            "uid": uid,
            "inode": inode,
            "is_lan": is_lan_or_local_ip(remote_ip),
        }
    return sockets


def _resolve_username(uid: int) -> str:
    if uid < 0:
        return "unknown"
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def _read_process_info(pid: str) -> dict[str, Any]:
    comm = ""
    cmdline = ""
    exe_path = ""
    owner = "unknown"
    try:
        with open(f"/proc/{pid}/comm", "r", encoding="utf-8") as fh:
            comm = fh.read().strip()
    except OSError:
        pass
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            raw = fh.read()
            cmdline = " ".join(part.decode("utf-8", errors="replace") for part in raw.split(b"\x00") if part).strip()
    except OSError:
        pass
    try:
        exe_path = os.readlink(f"/proc/{pid}/exe")
    except OSError:
        pass
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("Uid:"):
                    uid_str = line.split()[1]
                    if uid_str.isdigit():
                        owner = _resolve_username(int(uid_str))
                    break
    except OSError:
        pass
    return {
        "pid": int(pid),
        "comm": comm,
        "cmdline": cmdline,
        "exe_path": exe_path,
        "owner": owner,
    }


def _classify_app(proc_info: dict[str, Any]) -> tuple[str, str]:
    comm = proc_info["comm"]
    exe_path = proc_info["exe_path"]
    cmdline = proc_info["cmdline"]
    haystack = " ".join([os.path.basename(exe_path), comm, cmdline[:140]]).strip()

    for pattern, app_id, display_name in APP_CATALOG:
        if pattern.search(haystack):
            return app_id, display_name

    base = os.path.basename(exe_path) or comm
    if base:
        clean_id = re.sub(r"[^a-zA-Z0-9._-]+", "-", base.lower()).strip("-") or "unknown"
        return clean_id, base
    return "unknown-process", "Unknown Process"


def _read_ss_tcp_info_bytes() -> dict[tuple[str, int, str, int], tuple[int, int]]:
    """Query `ss -tin` for kernel tcp_info bytes_received & bytes_acked when netlink works."""
    ss_bin = shutil.which("ss")
    if not ss_bin:
        return {}
    try:
        res = subprocess.run(
            [ss_bin, "-tin", "state", "established"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if "Cannot open netlink socket" in (res.stderr or ""):
            return {}
        lines = (res.stdout or "").splitlines()
        out: dict[tuple[str, int, str, int], tuple[int, int]] = {}
        current_key = None
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if not line.startswith((" ", "\t")):
                cols = stripped.split()
                if len(cols) >= 4:
                    local_ep, remote_ep = cols[2], cols[3]
                    if ":" in local_ep and ":" in remote_ep:
                        lip, lport = local_ep.rsplit(":", 1)
                        rip, rport = remote_ep.rsplit(":", 1)
                        lip = lip.strip("[]")
                        rip = rip.strip("[]")
                        if lport.isdigit() and rport.isdigit():
                            current_key = (lip, int(lport), rip, int(rport))
            elif current_key is not None:
                rx_m = re.search(r"bytes_received:(\d+)", stripped)
                tx_m = re.search(r"bytes_acked:(\d+)", stripped)
                if rx_m or tx_m:
                    rx_b = int(rx_m.group(1)) if rx_m else 0
                    tx_b = int(tx_m.group(1)) if tx_m else 0
                    out[current_key] = (rx_b, tx_b)
                current_key = None
        return out
    except (OSError, subprocess.SubprocessError):
        return {}


def _match_interface_for_ip(local_ip: str, iface_snapshots: list[InterfaceSnapshot]) -> str | None:
    if not local_ip or local_ip in ("0.0.0.0", "::", "*"):
        return None
    norm = local_ip.replace("::ffff:", "")
    for snap in iface_snapshots:
        for addr in snap.ip_addresses:
            if addr.get("local") == norm or addr.get("local") == local_ip:
                return snap.iface
    return None


def collect_process_applications(
    iface_snapshots: list[InterfaceSnapshot],
    previous_socket_bytes: dict[tuple[str, int, str, int], tuple[int, int]],
    elapsed_sec: float,
    per_process_bytes_supported: bool,
    measurement_method: str,
) -> tuple[list[dict[str, Any]], dict[tuple[str, int, str, int], tuple[int, int]]]:
    """Enumerate all Linux processes holding network sockets via /proc/[PID]/fd."""
    all_sockets: dict[str, dict[str, Any]] = {}
    for path, proto, is_v6 in (
        ("/proc/net/tcp", "tcp", False),
        ("/proc/net/tcp6", "tcp6", True),
        ("/proc/net/udp", "udp", False),
        ("/proc/net/udp6", "udp6", True),
    ):
        all_sockets.update(_parse_proc_socket_table(path, proto, is_v6))

    ss_bytes_map = _read_ss_tcp_info_bytes() if per_process_bytes_supported else {}
    bytes_actually_measured = bool(ss_bytes_map)

    apps: dict[str, dict[str, Any]] = {}

    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        fd_dir = f"/proc/{entry}/fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue

        pid_inodes: list[str] = []
        for fd in fds:
            try:
                target = os.readlink(f"{fd_dir}/{fd}")
                if target.startswith("socket:[") and target.endswith("]"):
                    inode = target[8:-1]
                    if inode in all_sockets:
                        pid_inodes.append(inode)
            except OSError:
                continue

        if not pid_inodes:
            continue

        proc_info = _read_process_info(entry)
        app_id, app_name = _classify_app(proc_info)

        if app_id not in apps:
            apps[app_id] = {
                "app_id": app_id,
                "app_name": app_name,
                "exe_path": proc_info["exe_path"] or proc_info["comm"],
                "owner": proc_info["owner"],
                "pids": [],
                "active_sockets": 0,
                "tcp_established": 0,
                "udp_active": 0,
                "lan_sockets": 0,
                "internet_sockets": 0,
                "rx_delta": 0,
                "tx_delta": 0,
                "rx_rate_bps": 0.0,
                "tx_rate_bps": 0.0,
                "bytes_available": bytes_actually_measured,
                "measurement_source": measurement_method if bytes_actually_measured else "proc_socket_attribution_only",
                "connections": [],
                "interfaces": set(),
                "_seen_inodes": set(),
            }

        bucket = apps[app_id]
        if proc_info["pid"] not in bucket["pids"]:
            bucket["pids"].append(proc_info["pid"])
        if not bucket["exe_path"] and proc_info["exe_path"]:
            bucket["exe_path"] = proc_info["exe_path"]

        for inode in pid_inodes:
            if inode in bucket["_seen_inodes"]:
                continue
            bucket["_seen_inodes"].add(inode)
            sock = all_sockets[inode]
            bucket["active_sockets"] += 1
            if sock["proto"].startswith("tcp") and sock["state"] == "ESTABLISHED":
                bucket["tcp_established"] += 1
            elif sock["proto"].startswith("udp"):
                bucket["udp_active"] += 1

            if sock["state"] != "LISTEN":
                if sock["is_lan"]:
                    bucket["lan_sockets"] += 1
                else:
                    bucket["internet_sockets"] += 1

            bound_iface = _match_interface_for_ip(sock["local_ip"], iface_snapshots)
            if bound_iface:
                bucket["interfaces"].add(bound_iface)

            if bytes_actually_measured:
                key = (
                    sock["local_ip"].replace("::ffff:", ""),
                    sock["local_port"],
                    sock["remote_ip"].replace("::ffff:", ""),
                    sock["remote_port"],
                )
                if key in ss_bytes_map:
                    cur_rx, cur_tx = ss_bytes_map[key]
                    prev_rx, prev_tx = previous_socket_bytes.get(key, (cur_rx, cur_tx))
                    d_rx = max(0, cur_rx - prev_rx)
                    d_tx = max(0, cur_tx - prev_tx)
                    bucket["rx_delta"] += d_rx
                    bucket["tx_delta"] += d_tx

            bucket["connections"].append(
                {
                    "proto": sock["proto"],
                    "local": f"{sock['local_ip']}:{sock['local_port']}",
                    "remote": f"{sock['remote_ip']}:{sock['remote_port']}",
                    "state": sock["state"],
                    "scope": "lan" if sock["is_lan"] else "internet",
                    "iface": bound_iface or "unspecified",
                    "pid": proc_info["pid"],
                }
            )

    result: list[dict[str, Any]] = []
    safe_dt = max(elapsed_sec, 0.2)
    for bucket in apps.values():
        bucket.pop("_seen_inodes", None)
        bucket["interfaces"] = sorted(bucket["interfaces"])
        if bucket["bytes_available"]:
            bucket["rx_rate_bps"] = round(bucket["rx_delta"] / safe_dt, 2)
            bucket["tx_rate_bps"] = round(bucket["tx_delta"] / safe_dt, 2)
        else:
            bucket["rx_delta"] = None
            bucket["tx_delta"] = None
            bucket["rx_rate_bps"] = None
            bucket["tx_rate_bps"] = None
        result.append(bucket)

    result.sort(
        key=lambda a: (
            a["rx_delta"] or 0,
            a["tcp_established"],
            a["active_sockets"],
        ),
        reverse=True,
    )
    return result, ss_bytes_map
