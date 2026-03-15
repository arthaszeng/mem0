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
  "memverse-mcp:memverse/api"
  "auth-service:memverse/auth"
  "memverse-ui:memverse/ui"
  "concierge-mcp:concierge"
  "langgraph-agent:langgraph-agent"
)
IMAGE_PREFIX="memverse"

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

# Parse --service <name> from args; sets SVC_FILTER (empty = all services).
# Call: parse_service_filter "$@"
SVC_FILTER=""
parse_service_filter() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -s|--service) SVC_FILTER="$2"; shift 2 ;;
      *) shift ;;
    esac
  done
}

# Return SERVICES entries matching SVC_FILTER (or all if empty).
get_target_services() {
  if [[ -z "$SVC_FILTER" ]]; then
    echo "${SERVICES[@]}"
    return
  fi
  for entry in "${SERVICES[@]}"; do
    if [[ "$(svc_name "$entry")" == "$SVC_FILTER" ]]; then
      echo "$entry"
      return
    fi
  done
  log_error "Unknown service: $SVC_FILTER"
  log_info "Available: $(printf '%s ' "${SERVICES[@]}" | sed 's/:[^ ]*//g')"
  exit 1
}
