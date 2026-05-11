# ── Stage 1: Build ──────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# VITE_API_BASE="" means all /api/* calls are relative (proxied by nginx)
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE

RUN npm run build

# ── Stage 2: Serve ──────────────────────────────────────────
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
