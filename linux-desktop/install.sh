#!/usr/bin/env bash
set -euo pipefail

# NETSCOPE Installer for Ubuntu / Zorin OS / Linux Mint / Debian
PREFIX="/usr/lib/netscope"
BIN_PATH="/usr/bin/netscope"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Installing NETSCOPE to ${PREFIX}..."
sudo mkdir -p "${PREFIX}"
sudo cp -r "${ROOT_DIR}/netscope" "${PREFIX}/"
sudo cp "${ROOT_DIR}/linux-desktop/netscope_gui.py" "${PREFIX}/netscope_gui.py"
sudo cp "${ROOT_DIR}/linux-desktop/netscope_helper.py" "${PREFIX}/netscope_helper.py"
sudo chmod 755 "${PREFIX}/netscope_helper.py" "${PREFIX}/netscope/native_messaging/netscope_nmh.py"

sudo tee "${BIN_PATH}" > /dev/null <<'EOF'
#!/usr/bin/env bash
export NETSCOPE_DB_PATH="${HOME}/.local/share/netscope/netscope.db"
export NETSCOPE_LIVE_STATE="${HOME}/.local/share/netscope/live_state.json"
mkdir -p "${HOME}/.local/share/netscope"
exec /usr/bin/python3 /usr/lib/netscope/netscope_gui.py "$@"
EOF
sudo chmod 755 "${BIN_PATH}"

sudo install -Dm644 "${ROOT_DIR}/linux-desktop/desktop/netscope.desktop" /usr/share/applications/netscope.desktop
sudo install -Dm644 "${ROOT_DIR}/linux-desktop/desktop/netscope.svg" /usr/share/icons/hicolor/scalable/apps/netscope.svg
sudo install -Dm644 "${ROOT_DIR}/linux-desktop/polkit/com.netscope.helper.policy" /usr/share/polkit-1/actions/com.netscope.helper.policy
sudo install -Dm644 "${ROOT_DIR}/linux-desktop/systemd/netscope.service" /usr/lib/systemd/user/netscope.service

# Register Native Messaging Host for Chromium/Chrome/Brave/Edge
for nm_dir in \
  /etc/opt/chrome/native-messaging-hosts \
  /etc/chromium/native-messaging-hosts \
  /etc/opt/edge/native-messaging-hosts \
  /etc/brave/native-messaging-hosts; do
  sudo mkdir -p "${nm_dir}"
  sudo cp "${ROOT_DIR}/netscope/native_messaging/com.netscope.monitor.json" "${nm_dir}/com.netscope.monitor.json"
done

mkdir -p "${HOME}/.local/share/netscope"
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload || true
  systemctl --user enable --now netscope.service || true
fi

echo "NETSCOPE installed successfully. Launch from your application menu or run 'netscope'."
