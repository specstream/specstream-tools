#!/usr/bin/env bash
# Build step, last: clean the build server so that the snapshot holds nothing of its own, then
# power it off. Every server made from the snapshot gets new SSH host keys, a new machine id and
# runs the first-boot script again.
#
#   sudo bash scripts/clean-image.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root." >&2
  exit 1
fi

systemctl stop specstream-research.service nginx.service 2>/dev/null || true

# Nothing of a test deployment stays: password, certificate, key, reports.
rm -rf /etc/specstream-research/web-password /etc/specstream-research/provisioned /etc/specstream-research/tls
rm -rf /var/lib/specstream-research/api-key /var/lib/specstream-research/reports
rm -f /root/research-password.txt /var/log/specstream-research-provision.log

apt-get -y -q autoremove --purge
apt-get -y -q clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

rm -f /etc/ssh/ssh_host_*
rm -f /root/.ssh/authorized_keys /root/.bash_history /root/.lesshst /root/.viminfo
find /home -maxdepth 3 -name authorized_keys -delete 2>/dev/null || true

find /var/log -type f -name '*.gz' -delete
find /var/log -type f -regex '.*\.[0-9]+$' -delete
find /var/log -type f -exec truncate -s 0 {} +
journalctl --rotate >/dev/null 2>&1 || true
journalctl --vacuum-time=1s >/dev/null 2>&1 || true

truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id
cloud-init clean --logs --seed

sync
echo "Clean. Power the server off (shutdown -h now) and take the snapshot."
