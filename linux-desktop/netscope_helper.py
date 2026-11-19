#!/usr/bin/env python3
"""Minimal-privilege helper for NETSCOPE optional kernel accounting setup.

Never runs the GUI as root. Invoked via pkexec only when the user explicitly
requests kernel nftables/eBPF capability setup on Ubuntu/Debian/Zorin/Mint.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys


def setup_nftables_accounting() -> int:
    nft = shutil.which("nft")
    if not nft:
        sys.stderr.write("nftables (nft) is not installed on this system.\n")
        return 1
    script = """
table inet netscope_acct {
    chain output_acct {
        type filter hook output priority 0; policy accept;
        counter
    }
    chain input_acct {
        type filter hook input priority 0; policy accept;
        counter
    }
}
"""
    proc = subprocess.run([nft, "-f", "-"], input=script, text=True, capture_output=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or "Failed to configure nftables accounting table.\n")
        return proc.returncode
    print("Configured inet netscope_acct nftables counters.")
    return 0


def teardown_nftables_accounting() -> int:
    nft = shutil.which("nft")
    if not nft:
        return 0
    subprocess.run([nft, "delete", "table", "inet", "netscope_acct"], capture_output=True)
    return 0


def main() -> int:
    if os.geteuid() != 0:
        sys.stderr.write("netscope_helper must be run with elevated privileges (pkexec).\n")
        return 1
    parser = argparse.ArgumentParser(description="NETSCOPE Minimal Privileged Helper")
    parser.add_argument("action", choices=["setup-nft", "teardown-nft"])
    args = parser.parse_args()
    if args.action == "setup-nft":
        return setup_nftables_accounting()
    return teardown_nftables_accounting()


if __name__ == "__main__":
    raise SystemExit(main())
