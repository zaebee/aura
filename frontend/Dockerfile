# Stage 1: Build static assets
FROM oven/bun:1.1-alpine AS builder

WORKDIR /app

# Copy lockfile and package.json
COPY package.json bun.lock ./
RUN bun install

# Copy source and config
COPY . .

# Build the application
# Note: VITE_ variables are embedded at build time for SPAs
RUN bun run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Copy built assets to nginx html directory
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Healthy check
HEALTHCHECK --interval=30s --timeout=3s \
  CMD wget -qO- http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
