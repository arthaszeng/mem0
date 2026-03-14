#!/usr/bin/env bash
# Push amd64 images to Alibaba Cloud ACR.
# Images are tagged with both :VERSION-amd64 and :latest.
#
# Usage:
#   ./deploy/push.sh

source "$(dirname "$0")/config.sh"

log_step "Logging in to ACR (public endpoint)"
docker login --username="$ACR_USER" "$ACR_PUBLIC"

log_step "Tagging and pushing v${VERSION} images"
for entry in "${SERVICES[@]}"; do
  name=$(svc_name "$entry")
  local_tag="${IMAGE_PREFIX}/${name}:${VERSION}-amd64"
  acr_ver="${ACR_PUBLIC}/${ACR_NAMESPACE}/${name}:${VERSION}-amd64"
  acr_latest="${ACR_PUBLIC}/${ACR_NAMESPACE}/${name}:latest"

  log_info "Pushing ${name}..."
  docker tag "$local_tag" "$acr_ver"
  docker tag "$local_tag" "$acr_latest"
  docker push "$acr_ver"
  docker push "$acr_latest"
done

log_info "All images pushed to ACR: ${ACR_PUBLIC}/${ACR_NAMESPACE}/*"
