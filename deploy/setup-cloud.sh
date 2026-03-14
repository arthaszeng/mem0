#!/usr/bin/env bash
# One-time setup: migrate cloud server from ~/mem0/ (git repo) to ~/workspace/ (runtime only).
#
# This script:
#   1. Creates ~/workspace/ directory structure
#   2. Migrates .env.cloud -> ~/workspace/.env
#   3. Migrates nginx config and certs -> ~/workspace/nginx/
#   4. Syncs docker-compose.yml from local repo
#   5. Stops old standalone nginx container
#   6. Restarts all services under the new workspace
#   7. Verifies everything works
#
# Usage:
#   ./deploy/setup-cloud.sh
#
# IMPORTANT: This is destructive to the old layout. Run only once.

source "$(dirname "$0")/config.sh"

log_step "Checking current state on cloud"
ssh_cloud "
  echo 'Existing workspace:' && ls -la ~/workspace 2>/dev/null || echo '  (does not exist)'
  echo ''
  echo 'Old mem0 dir:' && ls ~/mem0/.env.cloud 2>/dev/null || echo '  (no .env.cloud)'
  echo 'Old nginx dir:' && ls ~/nginx/conf/nginx.conf 2>/dev/null || echo '  (no nginx.conf)'
"

log_step "Creating ~/workspace/ directory structure"
ssh_cloud "
  mkdir -p ~/workspace/nginx/cert
  mkdir -p ~/workspace/backup
  echo 'Directory structure created'
  find ~/workspace -type d
"

log_step "Migrating .env"
ssh_cloud "
  if [ -f ~/workspace/.env ]; then
    echo '.env already exists in workspace, keeping it'
  elif [ -f ~/mem0/.env.cloud ]; then
    cp ~/mem0/.env.cloud ~/workspace/.env
    echo 'Copied ~/mem0/.env.cloud -> ~/workspace/.env'
  else
    echo 'ERROR: No .env.cloud found to migrate!'
    exit 1
  fi

  # Ensure APP_VERSION is present
  if ! grep -q '^APP_VERSION=' ~/workspace/.env; then
    echo 'APP_VERSION=latest' >> ~/workspace/.env
    echo 'Added default APP_VERSION=latest'
  fi
"

log_step "Migrating nginx config and certs"
ssh_cloud "
  # Certs (these stay on the server, never in git)
  if [ -f ~/nginx/cert/arthaszeng.top.pem ]; then
    cp ~/nginx/cert/arthaszeng.top.pem ~/workspace/nginx/cert/
    cp ~/nginx/cert/arthaszeng.top.key ~/workspace/nginx/cert/
    echo 'Certs migrated'
  elif [ -f ~/workspace/nginx/cert/arthaszeng.top.pem ]; then
    echo 'Certs already in workspace'
  else
    echo 'WARNING: No SSL certs found!'
  fi
"

log_step "Syncing docker-compose.yml and nginx.conf from local repo"
scp_to_cloud "$SCRIPT_DIR/cloud/docker-compose.yml" "${CLOUD_WORKSPACE}/docker-compose.yml"
scp_to_cloud "$SCRIPT_DIR/cloud/nginx.conf"         "${CLOUD_WORKSPACE}/nginx/nginx.conf"

log_step "Migrating monitor.sh"
ssh_cloud "
  if [ -f ~/monitor.sh ]; then
    cp ~/monitor.sh ~/workspace/monitor.sh
    echo 'monitor.sh migrated'
  fi
"

log_step "Stopping old standalone nginx container"
ssh_cloud "
  docker stop nginx 2>/dev/null && docker rm nginx 2>/dev/null && echo 'Old nginx removed' || echo 'No standalone nginx to remove'
"

log_step "Stopping old docker-compose services (from ~/mem0/)"
ssh_cloud "
  if [ -f ~/mem0/docker-compose.cloud.yml ]; then
    cd ~/mem0
    docker compose -f docker-compose.cloud.yml down 2>&1 || true
    echo 'Old services stopped'
  fi
"

log_step "Starting services from ~/workspace/"
ssh_cloud "
  cd ~/workspace
  docker compose up -d 2>&1
"

log_step "Waiting 15s for services to initialize..."
sleep 15

log_step "Health checks"
ssh_cloud "
  echo 'Auth:      '  \$(curl -sf http://localhost:8760/auth/health || echo 'FAIL')
  echo 'Concierge: '  \$(curl -sf http://localhost:8767/concierge-mcp/health || echo 'FAIL')
  echo 'Nginx:     '  \$(curl -sf http://localhost/auth/health || echo 'FAIL')
  echo ''
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' | sort
"

log_step "Setup complete!"
log_info "Cloud workspace: ${CLOUD_HOST}:${CLOUD_WORKSPACE}/"
log_info "Old ~/mem0/ directory can be removed manually after verification."
log_warn "To remove: ssh admin@${CLOUD_HOST} 'rm -rf ~/mem0'"
