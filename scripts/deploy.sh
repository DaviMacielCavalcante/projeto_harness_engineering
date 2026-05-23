#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../infra/ansible"

echo "[deploy] bootstrap (Docker + Tailscale + NVIDIA)..."
ansible-playbook playbook-bootstrap.yml "$@"

echo "[deploy] deploy da aplicação..."
ansible-playbook playbook-deploy.yml "$@"

PC1_IP=$(grep -A2 'pc1:' inventory.yml | grep 'ansible_host' | awk '{print $2}')
echo "[deploy] concluído. Testa: curl http://${PC1_IP}:8000/health"
