# Base stage for common setup
FROM node:18-alpine AS base

RUN apk add --no-cache libc6-compat curl && \
    corepack enable && \
    corepack prepare pnpm@10.5.2 --activate

WORKDIR /app

FROM base AS deps

COPY package.json pnpm-lock.yaml ./

ARG NPM_REGISTRY=https://registry.npmjs.org/
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm config set registry ${NPM_REGISTRY} && \
    pnpm install --frozen-lockfile

FROM base AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/pnpm-lock.yaml ./pnpm-lock.yaml
COPY . .

RUN cp next.config.dev.mjs next.config.mjs
RUN cp .env.example .env

ARG NEXT_PUBLIC_BASE_PATH="/memory"
ENV NEXT_PUBLIC_BASE_PATH=${NEXT_PUBLIC_BASE_PATH}

ARG NODE_BUILD_MEM=1024
ENV NODE_OPTIONS="--max-old-space-size=${NODE_BUILD_MEM}"
RUN --mount=type=cache,target=/app/.next/cache \
    pnpm build

FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

COPY --chown=nextjs:nodejs entrypoint.sh /home/nextjs/entrypoint.sh
RUN chmod +x /home/nextjs/entrypoint.sh

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

ENTRYPOINT ["/home/nextjs/entrypoint.sh"]
CMD ["node", "server.js"]
