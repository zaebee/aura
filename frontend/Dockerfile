# Stage 1: Build static assets
FROM oven/bun:1.1-alpine AS builder

WORKDIR /app

# Copy lockfile and package.json from the frontend directory
# Context is the repository root
COPY frontend/package.json frontend/bun.lock ./
RUN bun install

# Copy configuration files first to leverage Docker cache
COPY frontend/tsconfig.json frontend/tsconfig.app.json frontend/tsconfig.node.json ./
COPY frontend/vite.config.ts frontend/tailwind.config.ts frontend/postcss.config.mjs frontend/eslint.config.js ./

# Copy source and config from the frontend directory
COPY frontend/public ./public
COPY frontend/src ./src
COPY frontend/index.html ./

# Build the application
# Note: VITE_ variables are embedded at build time for SPAs
RUN bun run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

RUN apk add --no-cache wget

# Copy built assets to nginx html directory
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Healthy check
HEALTHCHECK --interval=30s --timeout=3s \
  CMD wget -qO- http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
