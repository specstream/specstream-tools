#!/usr/bin/env bash
# First boot of a buyer's server: /var/lib/cloud/scripts/per-instance/provision.sh, run once by
# cloud-init. It reads the application variables from Vultr's metadata address, writes this
# server's own password and certificate, and starts the page.
#
# Application variables (set in the Vultr vendor portal, see ../listing/app.json):
#   web_pass             a password Vultr makes for each server; the page's password
#   specstream_api_key   the buyer's SpecStream API key; optional, the page can save it later
#
# No value of a variable is written to a log.
set -euo pipefail
umask 077

ETC="${RESEARCH_ETC_DIR:-/etc/specstream-research}"
DATA="${RESEARCH_DATA_DIR:-/var/lib/specstream-research}"
METADATA="${VULTR_METADATA_URL:-http://169.254.169.254}"
LOG="${RESEARCH_PROVISION_LOG:-/var/log/specstream-research-provision.log}"
GROUP="${RESEARCH_GROUP:-specstream-research}"
OWNER="${RESEARCH_USER:-specstream-research}"
NOTE="${RESEARCH_PASSWORD_NOTE:-/root/research-password.txt}"

exec >>"$LOG" 2>&1
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) provision starts"

if [ -f "$ETC/provisioned" ]; then
  echo "already provisioned; nothing to do"
  exit 0
fi

# One application variable, or nothing when it is not set or the address does not answer.
variable() {
  curl -fsS --max-time 10 --retry 5 --retry-delay 2 --retry-connrefused \
    -H "METADATA-TOKEN: vultr" "$METADATA/v1/internal/app-$1" 2>/dev/null || true
}

mkdir -p "$ETC/tls" "$DATA"

# The page's password. Without the variable (a server built by hand), make one and leave it for root.
password="$(variable web_pass)"
if [ -z "$password" ]; then
  password="$(openssl rand -hex 16)"
  printf '%s\n' "$password" >"$NOTE"
  chmod 0600 "$NOTE"
  echo "no web_pass variable; a password was written to $NOTE"
fi
printf '%s\n' "$password" >"$ETC/web-password"
unset password

# The buyer's SpecStream key, when it was typed at deployment.
key="$(variable specstream_api_key | tr -d '[:space:]')"
if [ -n "$key" ]; then
  printf '%s\n' "$key" >"$DATA/api-key"
  echo "the API key from the deployment was saved"
else
  echo "no API key at deployment; the page asks for it"
fi
unset key

# A certificate for this server's own address, valid for two years.
address="$(curl -fsS --max-time 10 "$METADATA/v1/interfaces/0/ipv4/address" 2>/dev/null || true)"
case "$address" in
  *[!0-9.]* | "") address="$(hostname -I 2>/dev/null | awk '{print $1}')" ;;
esac
case "$address" in
  *[!0-9.]* | "") address="127.0.0.1" ;;
esac
openssl req -x509 -newkey rsa:2048 -nodes -days 730 \
  -keyout "$ETC/tls/key.pem" -out "$ETC/tls/cert.pem" \
  -subj "/CN=$address" -addext "subjectAltName=IP:$address" >/dev/null 2>&1
echo "certificate made for $address"

if [ "$(id -u)" -eq 0 ]; then
  chown root:"$GROUP" "$ETC" "$ETC/web-password"
  chmod 0750 "$ETC"
  chmod 0640 "$ETC/web-password"
  chmod 0700 "$ETC/tls"
  chmod 0600 "$ETC/tls/key.pem"
  chown -R "$OWNER":"$GROUP" "$DATA"
  chmod 0700 "$DATA"

  if command -v ufw >/dev/null 2>&1; then
    ufw allow 80/tcp >/dev/null || true
    ufw allow 443/tcp >/dev/null || true
  fi
  systemctl enable --now nginx.service
  systemctl restart nginx.service
  systemctl enable specstream-research.service
  systemctl restart specstream-research.service
fi

date -u +%Y-%m-%dT%H:%M:%SZ >"$ETC/provisioned"
chmod 0644 "$ETC/provisioned" 2>/dev/null || true
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) provision ends"
