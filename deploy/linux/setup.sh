#!/usr/bin/env bash
# One-shot installer for a fresh Ubuntu/Debian server. Run as root:
#   bash setup.sh git@github.com:glebo309/GeckoPlotter.git
# Installs GeckoPlotter under /opt/gecko, runs it as a systemd service on port 8052 and
# keeps it running after crashes and reboots. Re-run it to update to the latest version.
set -euo pipefail

REPO="${1:?usage: bash setup.sh <git repo url>}"
APP_DIR=/opt/gecko
DATA_DIR=/var/lib/gecko
SERVICE_USER=gecko

apt-get update -qq
apt-get install -y -qq git python3 python3-venv python3-pip \
    libnss3 libatk-bridge2.0-0 libcups2 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libxkbcommon0 libpango-1.0-0 libasound2 >/dev/null

id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --create-home --home-dir "$DATA_DIR" "$SERVICE_USER"
mkdir -p "$DATA_DIR/autosave"
chown -R "$SERVICE_USER" "$DATA_DIR"

if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only
else
    git clone "$REPO" "$APP_DIR"
fi
chown -R "$SERVICE_USER" "$APP_DIR"

sudo -u "$SERVICE_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$SERVICE_USER" "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
sudo -u "$SERVICE_USER" "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt" gunicorn
# Image export (figures, PDF) needs a Chrome that kaleido can drive.
sudo -u "$SERVICE_USER" "$APP_DIR/.venv/bin/plotly_get_chrome" -y || echo "chrome download failed; figure export may not work"

cp "$APP_DIR/deploy/linux/gecko.service" /etc/systemd/system/gecko.service
systemctl daemon-reload
systemctl enable gecko >/dev/null
systemctl restart gecko
sleep 5
systemctl is-active gecko
echo "GeckoPlotter is running on port 8052. Logs: journalctl -u gecko -f"
