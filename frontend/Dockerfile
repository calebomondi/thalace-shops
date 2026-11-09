# The web app at shops.thalace.com: built with Bun, served by Caddy, which
# also forwards /api/* to the API over Railway's private network, so the
# browser sees one origin (as the Vite proxy does in dev).
FROM oven/bun:1.3.14 AS build
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY . .
# Railway passes service variables to Docker builds as build args. These are
# public values (the anon key is meant for browsers) baked into the bundle.
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
RUN bun run build

FROM caddy:2.10-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
