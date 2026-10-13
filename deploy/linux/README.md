# Run GeckoPlotter on a Linux server

For an always-on server (a university VM or a rented one) that is faster than the HPLC PC.
Needs Ubuntu or Debian, 2+ CPUs and 4+ GB RAM (8 GB if several people load Shimadzu `.lcd` runs).

1. On the server, make a read-only key so it can fetch the private repo:
   `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""` then `cat ~/.ssh/id_ed25519.pub`.
   Paste it on GitHub under the repo's Settings, Deploy keys (leave "write access" off).
2. Run as root: `bash setup.sh git@github.com:glebo309/GeckoPlotter.git`
   (or copy this folder over first; the script clones the repo itself).
3. Open `http://<server-address>:8052`.

Update: run the same command again. Logs: `journalctl -u gecko -f`. Slow actions are logged there too.

Autosaves live in `/var/lib/gecko/autosave`. Keep one copy of the app running; do not raise `--workers`.
There is no login. Keep the server on the university network (or behind its VPN), not open to the internet.
