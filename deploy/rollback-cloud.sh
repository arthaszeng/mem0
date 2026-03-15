#!/usr/bin/env bash
# Rollback cloud deployment to pre-upgrade images.
#
# Usage:
#   ./deploy/rollback-cloud.sh              # rollback to pre-upgrade tag
#   ./deploy/rollback-cloud.sh --full       # also restore database backups

source "$(dirname "$0")/config.sh"

FULL_ROLLBACK=false
[[ "${1:-}" == "--full" ]] && FULL_ROLLBACK=true

log_step "Rolling back cloud deployment"

# ── Step 1: Restore images ──
log_step "Restoring pre-upgrade images"
ssh_cloud "
  for svc in memverse-mcp memverse-ui auth-service concierge-mcp langgraph-agent; do
    if docker image inspect memverse/\${svc}:pre-upgrade >/dev/null 2>&1; then
      docker tag memverse/\${svc}:pre-upgrade memverse/\${svc}:latest
      echo \"  Restored mem0/\${svc}:latest\"
    else
      echo \"  WARN: mem0/\${svc}:pre-upgrade not found, skipping\"
    fi
  done
"

# ── Step 2: Restore .env backup ──
log_step "Restoring .env backup"
ssh_cloud "
  LATEST_BACKUP=\$(ls -td ${CLOUD_WORKSPACE}/backup/*-prev 2>/dev/null | head -1)
  if [ -n \"\$LATEST_BACKUP\" ] && [ -f \"\$LATEST_BACKUP/.env\" ]; then
    cp \"\$LATEST_BACKUP/.env\" ${CLOUD_WORKSPACE}/.env
    echo \"Restored .env from \$LATEST_BACKUP\"
  else
    echo 'WARN: No .env backup found'
  fi
"

# ── Step 3: Full rollback — restore databases ──
if [[ "$FULL_ROLLBACK" == true ]]; then
  log_step "Restoring database backups (--full)"
  ssh_cloud "
    LATEST_BACKUP=\$(ls -td ${CLOUD_WORKSPACE}/backup/*-prev 2>/dev/null | head -1)
    if [ -z \"\$LATEST_BACKUP\" ]; then
      echo 'ERROR: No backup directory found'
      exit 1
    fi

    cd ${CLOUD_WORKSPACE}
    docker compose stop memverse-mcp auth-service 2>/dev/null

    if [ -f \"\$LATEST_BACKUP/openmemory.db\" ]; then
      docker cp \"\$LATEST_BACKUP/openmemory.db\" workspace-memverse-mcp-1:/data/openmemory.db
      echo 'Restored openmemory.db'
    fi
    if [ -f \"\$LATEST_BACKUP/auth.db\" ]; then
      docker cp \"\$LATEST_BACKUP/auth.db\" workspace-auth-service-1:/data/auth.db
      echo 'Restored auth.db'
    fi
  "
fi

# ── Step 4: Restart ──
log_step "Restarting services"
ssh_cloud "
  cd ${CLOUD_WORKSPACE}
  docker compose down 2>&1
  docker compose up -d 2>&1
"

# ── Step 5: Health check ──
log_step "Waiting 15s..."
sleep 15

log_step "Health checks"
ssh_cloud "
  echo \"Auth:      \$(curl -sf http://localhost:8760/auth/health || echo FAIL)\"
  echo \"Concierge: \$(curl -sf http://localhost:8767/concierge-mcp/health || echo FAIL)\"
  echo ''
  docker ps --format 'table {{.Names}}\t{{.Status}}' | sort
"

log_info "Rollback complete."
