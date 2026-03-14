#!/usr/bin/env bash
# Shared configuration for all deploy scripts.
# Source this file: source "$(dirname "$0")/config.sh"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------- Version ----------
VERSION=$(cat "$PROJECT_ROOT/VERSION" | tr -d '[:space:]')

# ---------- Services (name:build_context) ----------
SERVICES=(
  "openmemory-mcp:openmemory/api"
  "auth-service:openmemory/auth"
  "openmemory-ui:openmemory/ui"
  "concierge-mcp:concierge"
)
IMAGE_PREFIX="mem0"

# ---------- ACR (Alibaba Cloud Container Registry) ----------
ACR_PUBLIC="crpi-xsgmoqneyleca8gg.cn-chengdu.personal.cr.aliyuncs.com"
ACR_VPC="crpi-xsgmoqneyleca8gg-vpc.cn-chengdu.personal.cr.aliyuncs.com"
ACR_NAMESPACE="arthaszeng"
ACR_USER="cheery_arthas"

# ---------- Cloud Server ----------
CLOUD_HOST="47.108.141.20"
CLOUD_USER="admin"
SSH_KEY="$HOME/.ssh/arthas"
CLOUD_WORKSPACE="/home/admin/workspace"

# ---------- Helpers ----------
ssh_cloud() {
  ssh -i "$SSH_KEY" -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
    "${CLOUD_USER}@${CLOUD_HOST}" "$@"
}

scp_to_cloud() {
  scp -i "$SSH_KEY" -o StrictHostKeyChecking=no "$1" \
    "${CLOUD_USER}@${CLOUD_HOST}:$2"
}

log_info()  { echo -e "\033[32m[INFO]\033[0m  $*"; }
log_warn()  { echo -e "\033[33m[WARN]\033[0m  $*"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $*"; }
log_step()  { echo -e "\n\033[36m===> $*\033[0m"; }

svc_name() { echo "${1%%:*}"; }
svc_ctx()  { echo "${1##*:}"; }
