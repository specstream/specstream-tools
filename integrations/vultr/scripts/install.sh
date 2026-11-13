#!/usr/bin/env bash
# Build step: put the research agent on a new Ubuntu 24.04 server, before the snapshot is taken.
#
#   sudo bash scripts/install.sh        run from this folder's parent (integrations/vultr), as root
#
# It installs nginx, the agent (app/research_agent.py, Python's standard library only), its service
# and the first-boot script. It writes no password, no key and no certificate: those belong to
# each buyer's server and are made on its first boot by scripts/provision.sh.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends nginx openssl curl ca-certificates python3

if ! id specstream-research >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/specstream-research --shell /usr/sbin/nologin specstream-research
fi

install -d -m 0755 /opt/specstream-research
install -m 0644 "$HERE/app/research_agent.py" /opt/specstream-research/research_agent.py
install -d -m 0750 -o root -g specstream-research /etc/specstream-research
install -d -m 0700 -o specstream-research -g specstream-research /var/lib/specstream-research

install -m 0644 "$HERE/files/specstream-research.service" /etc/systemd/system/specstream-research.service
install -m 0644 "$HERE/files/nginx.conf" /etc/nginx/sites-available/specstream-research
ln -sf /etc/nginx/sites-available/specstream-research /etc/nginx/sites-enabled/specstream-research
rm -f /etc/nginx/sites-enabled/default

# The command line: specstream-research "question" --depth quick
cat >/usr/local/bin/specstream-research <<'SH'
#!/bin/sh
# One research report as Markdown on standard output. Run it as root.
RESEARCH_DATA_DIR=/var/lib/specstream-research exec runuser -u specstream-research -- \
  env RESEARCH_DATA_DIR=/var/lib/specstream-research /usr/bin/python3 /opt/specstream-research/research_agent.py ask "$@"
SH
chmod 0755 /usr/local/bin/specstream-research

# cloud-init runs this once on each new server made from the snapshot.
install -d -m 0755 /var/lib/cloud/scripts/per-instance
install -m 0755 "$HERE/scripts/provision.sh" /var/lib/cloud/scripts/per-instance/provision.sh

systemctl daemon-reload
systemctl enable specstream-research.service
# nginx waits for the certificate of the buyer's server; provision.sh starts it.
systemctl disable --now nginx.service

echo "Installed. Next: sudo bash scripts/clean-image.sh, then take the snapshot."
