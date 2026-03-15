#!/usr/bin/env bash
# Deploy to cloud server via SSH.
# The cloud server only pulls images and runs services — no source code needed.
#
# Usage:
#   ./deploy/deploy-cloud.sh                              # full: build + push + deploy (all)
#   ./deploy/deploy-cloud.sh -s memverse-mcp              # full: single service only
#   ./deploy/deploy-cloud.sh --skip-build                 # skip build, still push + deploy
#   ./deploy/deploy-cloud.sh --skip-build --skip-push     # just deploy (images already in ACR)
#   ./deploy/deploy-cloud.sh --skip-build --skip-push -s memverse-mcp

source "$(dirname "$0")/config.sh"
parse_service_filter "$@"

SKIP_BUILD=false
SKIP_PUSH=false
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=true ;;
    --skip-push)  SKIP_PUSH=true ;;
  esac
done

targets=( $(get_target_services) )
svc_names=()
for entry in "${targets[@]}"; do
  svc_names+=( "$(svc_name "$entry")" )
done
svc_list="${svc_names[*]}"

if [[ -n "$SVC_FILTER" ]]; then
  log_info "Target service: ${SVC_FILTER}"
else
  log_info "Target services: ${svc_list}"
fi

# ── Step 1: Build ──
if [[ "$SKIP_BUILD" == false ]]; then
  if [[ -n "$SVC_FILTER" ]]; then
    "$SCRIPT_DIR/build.sh" --cloud -s "$SVC_FILTER"
  else
    "$SCRIPT_DIR/build.sh" --cloud
  fi
else
  log_info "Skipping build (--skip-build)"
fi

# ── Step 2: Push ──
if [[ "$SKIP_PUSH" == false ]]; then
  if [[ -n "$SVC_FILTER" ]]; then
    "$SCRIPT_DIR/push.sh" -s "$SVC_FILTER"
  else
    "$SCRIPT_DIR/push.sh"
  fi
else
  log_info "Skipping push (--skip-push)"
fi

# ── Step 3: Sync config files to cloud ──
log_step "Syncing config to ${CLOUD_HOST}:${CLOUD_WORKSPACE}/"
ssh_cloud "mkdir -p ${CLOUD_WORKSPACE}/nginx ${CLOUD_WORKSPACE}/backup"
scp_to_cloud "$SCRIPT_DIR/cloud/docker-compose.yml" "${CLOUD_WORKSPACE}/docker-compose.yml"
scp_to_cloud "$SCRIPT_DIR/cloud/nginx.conf"         "${CLOUD_WORKSPACE}/nginx/nginx.conf"

# ── Step 4: Backup on cloud ──
log_step "Backing up current state on cloud"
ssh_cloud "
  BACKUP_DIR=${CLOUD_WORKSPACE}/backup/${VERSION}-prev
  mkdir -p \$BACKUP_DIR

  # Backup images
  for svc in ${svc_list}; do
    docker tag \"memverse/\${svc}:latest\" \"memverse/\${svc}:pre-upgrade\" 2>/dev/null || true
  done

  # Backup databases (always, regardless of target service)
  docker cp workspace-memverse-mcp-1:/data/openmemory.db \$BACKUP_DIR/openmemory.db 2>/dev/null || true
  docker cp workspace-auth-service-1:/data/auth.db         \$BACKUP_DIR/auth.db 2>/dev/null || true

  # Backup env
  cp ${CLOUD_WORKSPACE}/.env \$BACKUP_DIR/.env 2>/dev/null || true

  # Record image digests
  for svc in ${svc_list}; do
    echo \"\${svc}: \$(docker inspect --format='{{.Id}}' memverse/\${svc}:latest 2>/dev/null || echo 'N/A')\"
  done > \$BACKUP_DIR/image-digests.txt

  echo 'Backup complete'
"

# ── Step 5: Pull images from ACR (VPC internal) ──
log_step "Pulling v${VERSION} images on cloud (ACR VPC)"
ssh_cloud "
  sudo docker login --username=${ACR_USER} ${ACR_VPC} 2>&1 | tail -1

  for svc in ${svc_list}; do
    echo \"Pulling \${svc}...\"
    sudo docker pull ${ACR_VPC}/${ACR_NAMESPACE}/\${svc}:${VERSION}-amd64 2>&1 | tail -1
    docker tag ${ACR_VPC}/${ACR_NAMESPACE}/\${svc}:${VERSION}-amd64 memverse/\${svc}:${VERSION}
    docker tag ${ACR_VPC}/${ACR_NAMESPACE}/\${svc}:${VERSION}-amd64 memverse/\${svc}:latest
  done

  echo 'Pull and retag complete'
"

# ── Step 6: Update APP_VERSION in .env ──
log_step "Updating APP_VERSION=${VERSION} on cloud"
ssh_cloud "
  ENV_FILE=${CLOUD_WORKSPACE}/.env
  if [ ! -f \$ENV_FILE ]; then
    echo 'ERROR: .env not found at ${CLOUD_WORKSPACE}/.env'
    echo 'Run setup-cloud.sh first to initialize the workspace.'
    exit 1
  fi
  if grep -q '^APP_VERSION=' \$ENV_FILE; then
    sed -i \"s/^APP_VERSION=.*/APP_VERSION=${VERSION}/\" \$ENV_FILE
  else
    echo \"APP_VERSION=${VERSION}\" >> \$ENV_FILE
  fi
  grep APP_VERSION \$ENV_FILE
"

# ── Step 7: Restart services ──
# Use --force-recreate instead of down+up to minimize downtime.
# For single service: --no-deps avoids restarting dependencies.
log_step "Restarting services"
if [[ -n "$SVC_FILTER" ]]; then
  ssh_cloud "
    cd ${CLOUD_WORKSPACE}
    docker compose up -d --force-recreate --no-deps ${SVC_FILTER} 2>&1
  "
else
  ssh_cloud "
    cd ${CLOUD_WORKSPACE}
    docker compose up -d --force-recreate 2>&1
  "
fi

# ── Step 8: Wait and health check ──
log_step "Waiting 15s for services to initialize..."
sleep 15

log_step "Health checks"
HEALTH_OK=true
check_health() {
  local name=$1 url=$2
  result=$(ssh_cloud "curl -sf '$url' 2>/dev/null" || echo "FAIL")
  if [[ "$result" == "FAIL" ]]; then
    log_error "${name}: FAILED"
    HEALTH_OK=false
  else
    log_info "${name}: OK — ${result}"
  fi
}

check_health "Auth"      "http://localhost:8760/auth/health"
check_health "Concierge" "http://localhost:8767/concierge-mcp/health"

# Check containers
ssh_cloud "docker compose -f ${CLOUD_WORKSPACE}/docker-compose.yml ps --format 'table {{.Name}}\t{{.Status}}' 2>/dev/null" \
  || ssh_cloud "cd ${CLOUD_WORKSPACE} && docker compose ps"

if [[ "$HEALTH_OK" == true ]]; then
  log_info "Deploy v${VERSION} successful! (${svc_list})"
else
  log_error "Some health checks failed. Consider rolling back: ./deploy/rollback-cloud.sh"
  exit 1
fi
