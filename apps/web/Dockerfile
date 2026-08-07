# Development image: `next dev` with bind-mounted source for hot reload, not an
# optimized production build — see docs/engineering/07-docker-strategy.md.
FROM node:22-slim

RUN corepack enable

WORKDIR /app
COPY . .
RUN pnpm install --frozen-lockfile

WORKDIR /app/apps/web
EXPOSE 3000

CMD ["pnpm", "dev"]
