#!/bin/sh
set -e

cd /app

# Replace %%NEXT_PUBLIC_*%% placeholders baked at build time
# with actual runtime environment variable values.
# This allows the same image to run in any environment.
printenv | grep '^NEXT_PUBLIC_' | while IFS='=' read -r key rest; do
  value=$(printenv "$key")
  placeholder="%%${key}%%"
  if [ -n "$value" ] && [ "$value" != "$placeholder" ]; then
    find .next/ -type f \( -name '*.js' -o -name '*.json' -o -name '*.html' \) \
      -exec sed -i "s|${placeholder}|${value}|g" {} +
  fi
done

echo "Done replacing env variable placeholders with real values"

exec "$@"
