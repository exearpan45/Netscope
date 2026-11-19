#!/usr/bin/env bash
set -euo pipefail

echo "Stopping and disabling NETSCOPE background service..."
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now netscope.service 2>/dev/null || true
fi

sudo rm -rf /usr/lib/netscope
sudo rm -f /usr/bin/netscope
sudo rm -f /usr/share/applications/netscope.desktop
sudo rm -f /usr/share/icons/hicolor/scalable/apps/netscope.svg
sudo rm -f /usr/share/polkit-1/actions/com.netscope.helper.policy
sudo rm -f /usr/lib/systemd/user/netscope.service

for nm_dir in \
  /etc/opt/chrome/native-messaging-hosts \
  /etc/chromium/native-messaging-hosts \
  /etc/opt/edge/native-messaging-hosts \
  /etc/brave/native-messaging-hosts; do
  sudo rm -f "${nm_dir}/com.netscope.monitor.json"
done

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload 2>/dev/null || true
fi

echo "NETSCOPE cleanly uninstalled. User database preserved at ~/.local/share/netscope (remove manually if desired)."
