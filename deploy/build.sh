#!/usr/bin/env bash
# Build Docker images for local (arm64) or cloud (amd64) deployment.
#
# Usage:
#   ./deploy/build.sh --local   # arm64, for Mac Mini dev
#   ./deploy/build.sh --cloud   # amd64, for cloud server
#   ./deploy/build.sh           # defaults to --cloud

source "$(dirname "$0")/config.sh"

TARGET="${1:---cloud}"

case "$TARGET" in
  --local)
    log_step "Building local (arm64) images v${VERSION}"
    cd "$PROJECT_ROOT"
    APP_VERSION="$VERSION" docker compose -f docker-compose.local.yml build
    log_info "Local build complete. Images tagged as mem0/<service>:${VERSION}"
    ;;

  --cloud)
    log_step "Building cloud (amd64) images v${VERSION}"
    for entry in "${SERVICES[@]}"; do
      name=$(svc_name "$entry")
      ctx=$(svc_ctx "$entry")
      tag="${IMAGE_PREFIX}/${name}:${VERSION}-amd64"
      log_info "Building ${name} -> ${tag}"
      docker build --platform linux/amd64 \
        --build-arg APP_VERSION="$VERSION" \
        -t "$tag" \
        "$PROJECT_ROOT/$ctx"
    done
    log_info "Cloud build complete. All images tagged as mem0/<service>:${VERSION}-amd64"
    ;;

  *)
    log_error "Unknown target: $TARGET"
    echo "Usage: $0 [--local|--cloud]"
    exit 1
    ;;
esac
