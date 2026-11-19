#!/usr/bin/env bash
set -euo pipefail

# Builds a genuine Debian (.deb) package for Ubuntu / Zorin OS / Linux Mint / Debian
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="1.0.1"
PKG_NAME="netscope_${VERSION}_amd64"
BUILD_DIR="${ROOT_DIR}/dist-deb/${PKG_NAME}"

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/usr/lib/netscope"
mkdir -p "${BUILD_DIR}/usr/bin"
mkdir -p "${BUILD_DIR}/usr/share/applications"
mkdir -p "${BUILD_DIR}/usr/share/icons/hicolor/scalable/apps"
mkdir -p "${BUILD_DIR}/usr/share/polkit-1/actions"
mkdir -p "${BUILD_DIR}/usr/lib/systemd/user"

cp -r "${ROOT_DIR}/netscope" "${BUILD_DIR}/usr/lib/netscope/"
cp "${ROOT_DIR}/linux-desktop/netscope_gui.py" "${BUILD_DIR}/usr/lib/netscope/"
cp "${ROOT_DIR}/linux-desktop/netscope_helper.py" "${BUILD_DIR}/usr/lib/netscope/"
chmod 755 "${BUILD_DIR}/usr/lib/netscope/netscope_helper.py" "${BUILD_DIR}/usr/lib/netscope/netscope/native_messaging/netscope_nmh.py"

cat > "${BUILD_DIR}/usr/bin/netscope" <<'EOF'
#!/usr/bin/env bash
export NETSCOPE_DB_PATH="${HOME}/.local/share/netscope/netscope.db"
export NETSCOPE_LIVE_STATE="${HOME}/.local/share/netscope/live_state.json"
mkdir -p "${HOME}/.local/share/netscope"
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload >/dev/null 2>&1 || true
  systemctl --user start netscope.service >/dev/null 2>&1 || true
fi
exec /usr/bin/python3 /usr/lib/netscope/netscope_gui.py "$@"
EOF
chmod 755 "${BUILD_DIR}/usr/bin/netscope"

cp "${ROOT_DIR}/linux-desktop/desktop/netscope.desktop" "${BUILD_DIR}/usr/share/applications/netscope.desktop"
cp "${ROOT_DIR}/linux-desktop/desktop/netscope.svg" "${BUILD_DIR}/usr/share/icons/hicolor/scalable/apps/netscope.svg"
cp "${ROOT_DIR}/linux-desktop/polkit/com.netscope.helper.policy" "${BUILD_DIR}/usr/share/polkit-1/actions/com.netscope.helper.policy"
cp "${ROOT_DIR}/linux-desktop/systemd/netscope.service" "${BUILD_DIR}/usr/lib/systemd/user/netscope.service"

cat > "${BUILD_DIR}/DEBIAN/control" <<EOF
Package: netscope
Version: ${VERSION}
Section: net
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.10), python3-pyqt6, iproute2
Recommends: libnotify-bin, nftables
Maintainer: NETSCOPE Engineering <support@netscope.local>
Description: NETSCOPE Linux Network Monitor
 Real-time interface usage monitor with process and optional browser telemetry.
 Per-process byte accounting depends on kernel and permission capabilities.
EOF

cat > "${BUILD_DIR}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q || true
fi
exit 0
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"

cat > "${BUILD_DIR}/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
  if command -v pkill >/dev/null 2>&1; then
    pkill -f "netscope.daemon" || true
  fi
fi
exit 0
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/prerm"

dpkg-deb --build "${BUILD_DIR}" "${ROOT_DIR}/dist-deb/${PKG_NAME}.deb"
echo "Built Debian package: ${ROOT_DIR}/dist-deb/${PKG_NAME}.deb"
