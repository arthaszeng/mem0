#!/usr/bin/env bash
# Build Docker images for local (arm64) or cloud (amd64) deployment.
#
# Usage:
#   ./deploy/build.sh --local                    # all services, arm64
#   ./deploy/build.sh --cloud                    # all services, amd64
#   ./deploy/build.sh --cloud -s memverse-mcp    # single service, amd64
#   ./deploy/build.sh --local -s memverse-mcp    # single service, arm64

source "$(dirname "$0")/config.sh"

TARGET=""
for arg in "$@"; do
  case "$arg" in
    --local|--cloud) TARGET="$arg" ;;
  esac
done
TARGET="${TARGET:---cloud}"
parse_service_filter "$@"

case "$TARGET" in
  --local)
    if [[ -n "$SVC_FILTER" ]]; then
      log_step "Building local (arm64) ${SVC_FILTER} v${VERSION}"
      cd "$PROJECT_ROOT"
      APP_VERSION="$VERSION" docker compose -f docker-compose.local.yml build "$SVC_FILTER"
    else
      log_step "Building local (arm64) images v${VERSION}"
      cd "$PROJECT_ROOT"
      APP_VERSION="$VERSION" docker compose -f docker-compose.local.yml build
    fi
    log_info "Local build complete. Images tagged as memverse/<service>:${VERSION}"
    ;;

  --cloud)
    targets=( $(get_target_services) )
    log_step "Building cloud (amd64) images v${VERSION}"
    for entry in "${targets[@]}"; do
      name=$(svc_name "$entry")
      ctx=$(svc_ctx "$entry")
      tag="${IMAGE_PREFIX}/${name}:${VERSION}-amd64"
      log_info "Building ${name} -> ${tag}"
      docker build --platform linux/amd64 \
        --build-arg APP_VERSION="$VERSION" \
        -t "$tag" \
        "$PROJECT_ROOT/$ctx"
    done
    log_info "Cloud build complete. All images tagged as memverse/<service>:${VERSION}-amd64"
    ;;

  *)
    log_error "Unknown target: $TARGET"
    echo "Usage: $0 [--local|--cloud] [-s|--service <name>]"
    exit 1
    ;;
esac
