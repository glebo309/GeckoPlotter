#!/bin/bash
# One double-click: installs a private Python (uv) on the first run, fetches the newest GeckoPlotter from GitHub,
# starts it on this computer and opens it in the browser. Nothing is installed system-wide.
RAW="https://raw.githubusercontent.com/glebo309/GeckoPlotter/main/deploy/launcher"
HOME_DIR="$HOME/Library/Application Support/GeckoPlotter"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
mkdir -p "$HOME_DIR"
# Keep a copy of this script next to the app: the GeckoPlotter shortcut runs that one.
[ "$(cd "$(dirname "$0")" && pwd)" = "$HOME_DIR" ] || cp "$0" "$HOME_DIR/start-mac.command"

if ! command -v uv >/dev/null 2>&1; then
  echo "Setting up GeckoPlotter for the first time. This needs the internet and takes a minute..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

# Newest launcher (if GitHub cannot be reached, the copy already on this computer is used)
for f in launcher.py splash.html; do
  curl -fsSL --max-time 15 "$RAW/$f" -o "$HOME_DIR/$f.new" 2>/dev/null && mv -f "$HOME_DIR/$f.new" "$HOME_DIR/$f" || rm -f "$HOME_DIR/$f.new"
done

if ! command -v uv >/dev/null 2>&1 || [ ! -f "$HOME_DIR/launcher.py" ]; then
  echo; echo "GeckoPlotter could not be set up. Check the internet connection and open this file again."
  read -r -p "Press Return to close. " _; exit 1
fi
uv run --python 3.12 --no-project "$HOME_DIR/launcher.py"
echo; read -r -p "Press Return to close. " _
