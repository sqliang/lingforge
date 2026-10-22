FROM node:20-alpine AS build
WORKDIR /app
COPY pnpm-workspace.yaml pnpm-lock.yaml ./
COPY frontend/package.json frontend/package.json
# Pin pnpm explicitly: Node 20 Corepack otherwise resolves its newest default,
# which currently requires Node 22 and fails before dependency installation.
RUN corepack enable && corepack prepare pnpm@10.33.1 --activate && pnpm install --frozen-lockfile --filter @lingforge/frontend
COPY frontend/ frontend/
WORKDIR /app/frontend
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_API_BASE_URL
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN pnpm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=build /app/frontend/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
