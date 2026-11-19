"""Real Linux capability probing for NETSCOPE.

Determines which kernel and system accounting interfaces are genuinely
available on the current Linux host without ever fabricating support.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass


@dataclass
class SystemCapabilities:
    hostname: str
    kernel_release: str
    architecture: str
    distro_name: str
    uid: int
    is_root: bool
    proc_net_dev: bool
    proc_net_sockets: bool
    proc_pid_fd: bool
    ip_addr_json: bool
    ss_available: bool
    ss_tcp_info_bytes: bool
    netlink_sock_diag: bool
    ebpf_btf: bool
    ebpf_bcc: bool
    nftables_available: bool
    conntrack_available: bool
    vnstat_db_available: bool
    networkmanager_available: bool
    notify_send_available: bool
    pyside6_available: bool
    per_process_byte_method: str
    per_process_bytes_available: bool
    limitations: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _read_distro_name() -> str:
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return f"{platform.system()} {platform.release()}"


def _check_proc_pid_fd_readable() -> bool:
    try:
        os.listdir("/proc/self/fd")
        # Also verify at least one other PID if possible
        for entry in os.listdir("/proc"):
            if entry.isdigit() and entry != str(os.getpid()):
                try:
                    os.listdir(f"/proc/{entry}/fd")
                    return True
                except OSError:
                    continue
        return True
    except OSError:
        return False


def _probe_ss_capabilities() -> tuple[bool, bool, bool]:
    """Return (ss_available, netlink_sock_diag, ss_tcp_info_bytes)."""
    ss_bin = shutil.which("ss")
    if not ss_bin:
        return False, False, False
    try:
        proc = subprocess.run(
            [ss_bin, "-tin", "state", "established"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        stderr = proc.stderr or ""
        stdout = proc.stdout or ""
        netlink_ok = "Cannot open netlink socket" not in stderr
        has_bytes = ("bytes_received:" in stdout) or ("bytes_acked:" in stdout)
        return True, netlink_ok, has_bytes
    except (OSError, subprocess.SubprocessError):
        return False, False, False


def _check_python_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def detect_capabilities() -> SystemCapabilities:
    uid = os.geteuid()
    is_root = uid == 0
    proc_net_dev = os.path.isfile("/proc/net/dev") and os.access("/proc/net/dev", os.R_OK)
    proc_net_sockets = all(
        os.path.isfile(p) and os.access(p, os.R_OK)
        for p in ("/proc/net/tcp", "/proc/net/udp")
    )
    proc_pid_fd = _check_proc_pid_fd_readable()
    ip_bin = shutil.which("ip")
    ip_addr_json = bool(ip_bin)
    ss_available, netlink_sock_diag, ss_tcp_info_bytes = _probe_ss_capabilities()
    ebpf_btf = os.path.exists("/sys/kernel/btf/vmlinux")
    ebpf_bcc = _check_python_module("bcc")
    nftables_available = bool(shutil.which("nft")) and is_root
    conntrack_available = os.path.exists("/proc/net/nf_conntrack") and os.access(
        "/proc/net/nf_conntrack", os.R_OK
    )
    vnstat_db_available = os.path.exists("/var/lib/vnstat/vnstat.db") and os.access(
        "/var/lib/vnstat/vnstat.db", os.R_OK
    )
    networkmanager_available = bool(shutil.which("nmcli")) or os.path.exists(
        "/var/lib/NetworkManager"
    )
    notify_send_available = bool(shutil.which("notify-send"))
    pyside6_available = _check_python_module("PySide6")

    limitations: list[str] = []

    if ss_tcp_info_bytes:
        per_process_byte_method = "kernel_tcp_info_sock_diag"
        per_process_bytes_available = True
    elif ebpf_btf and ebpf_bcc and is_root:
        per_process_byte_method = "ebpf_kprobe_tcp_udp"
        per_process_bytes_available = True
    else:
        per_process_byte_method = "proc_socket_attribution_only"
        per_process_bytes_available = False
        if not netlink_sock_diag:
            limitations.append(
                "Kernel netlink SOCK_DIAG is unavailable in this environment; per-socket tcp_info byte counters (bytes_received/bytes_acked) cannot be queried."
            )
        elif not ss_tcp_info_bytes:
            limitations.append(
                "No active TCP sockets reported kernel tcp_info byte counters (or kernel lacks CONFIG_INET_TCP_DIAG byte accounting)."
            )
        if not (ebpf_btf and ebpf_bcc and is_root):
            limitations.append(
                "eBPF per-process kprobe/cgroup accounting is unavailable (requires BTF, python3-bcc, and CAP_BPF/root helper)."
            )
        limitations.append(
            "Per-application active sockets, PIDs, owners, executable paths, and bound interfaces are measured live from /proc; per-application byte totals are marked 'Not available with current permissions or system capabilities' rather than estimated."
        )

    if not vnstat_db_available:
        limitations.append(
            "No pre-existing vnStat database (/var/lib/vnstat/vnstat.db) found; historical per-application usage unavailable before NETSCOPE installation."
        )

    if not conntrack_available:
        limitations.append(
            "Kernel nf_conntrack (/proc/net/nf_conntrack) is unavailable; NAT flow byte counters cannot be read."
        )

    return SystemCapabilities(
        hostname=platform.node() or "linux-host",
        kernel_release=platform.release(),
        architecture=platform.machine(),
        distro_name=_read_distro_name(),
        uid=uid,
        is_root=is_root,
        proc_net_dev=proc_net_dev,
        proc_net_sockets=proc_net_sockets,
        proc_pid_fd=proc_pid_fd,
        ip_addr_json=ip_addr_json,
        ss_available=ss_available,
        ss_tcp_info_bytes=ss_tcp_info_bytes,
        netlink_sock_diag=netlink_sock_diag,
        ebpf_btf=ebpf_btf,
        ebpf_bcc=ebpf_bcc,
        nftables_available=nftables_available,
        conntrack_available=conntrack_available,
        vnstat_db_available=vnstat_db_available,
        networkmanager_available=networkmanager_available,
        notify_send_available=notify_send_available,
        pyside6_available=pyside6_available,
        per_process_byte_method=per_process_byte_method,
        per_process_bytes_available=per_process_bytes_available,
        limitations=limitations,
    )
