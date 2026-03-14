#!/usr/bin/env bash
# Build and deploy locally on Mac Mini (arm64).
#
# Usage:
#   ./deploy/deploy-local.sh           # build + up
#   ./deploy/deploy-local.sh --up-only # skip build, just restart

source "$(dirname "$0")/config.sh"

cd "$PROJECT_ROOT"

if [[ "${1:-}" != "--up-only" ]]; then
  log_step "Building local images"
  "$SCRIPT_DIR/build.sh" --local
fi

log_step "Starting local services"
APP_VERSION="$VERSION" docker compose -f docker-compose.local.yml up -d

log_step "Services running (v${VERSION})"
docker compose -f docker-compose.local.yml ps
