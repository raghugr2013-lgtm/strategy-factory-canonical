#!/usr/bin/env bash
# Strategy Factory — one-shot VPS bootstrap.
# Installs everything the deployment scripts assume, on Ubuntu 24.04.
# Idempotent: safe to run more than once.
#
# Usage:  sudo ./infra/scripts/bootstrap-vps.sh
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "error: must run as root (sudo)" >&2
  exit 1
fi

echo "[bootstrap] apt update + core tools"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl gnupg lsb-release git jq openssl \
  net-tools ufw

if ! command -v docker >/dev/null 2>&1; then
  echo "[bootstrap] installing Docker Engine + Compose plugin (official repo)"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
else
  echo "[bootstrap] Docker already installed → $(docker --version)"
fi

echo "[bootstrap] docker compose plugin → $(docker compose version || true)"

echo "[bootstrap] ensuring vqb-network exists"
docker network inspect vqb-network >/dev/null 2>&1 || docker network create vqb-network

# Add the invoking user (via SUDO_USER) to the docker group for convenience.
if [[ -n "${SUDO_USER:-}" ]] && ! id -nG "$SUDO_USER" | grep -qw docker; then
  usermod -aG docker "$SUDO_USER"
  echo "[bootstrap] added $SUDO_USER to docker group — log out/in for it to take effect"
fi

echo "[bootstrap] done — proceed with:  ./infra/scripts/precheck.sh && ./infra/scripts/deploy.sh"
