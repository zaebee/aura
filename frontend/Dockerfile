# Stage 1: Build static assets
# Pin a full bun patch (not the floating 1.1 tag): the repo's bun.lock uses the
# text format (lockfileVersion 1) written by bun 1.3.x, which older 1.1.x patches
# fail to parse ("Unknown lockfile version"). Keep this aligned with the bun used
# to author the lockfile.
FROM oven/bun:1.3.14-alpine AS builder

WORKDIR /app

# Install buf
RUN apk add --no-cache curl && \
    BUF_VERSION="1.47.2" && \
    curl -fsSL --retry 3 --retry-delay 2 \
        "https://github.com/bufbuild/buf/releases/download/v${BUF_VERSION}/buf-Linux-x86_64" \
        -o "/usr/local/bin/buf" && \
    chmod +x "/usr/local/bin/buf"

# Copy workspace files for buf
COPY buf.yaml buf.gen.yaml ./
COPY proto ./proto

# Copy lockfile and package.json from the frontend directory
COPY frontend/package.json frontend/bun.lock ./frontend/
RUN cd frontend && bun install --frozen-lockfile

# Copy configuration files
COPY frontend/tsconfig.json frontend/tsconfig.app.json frontend/tsconfig.node.json ./frontend/
COPY frontend/vite.config.ts frontend/tailwind.config.ts frontend/postcss.config.mjs frontend/eslint.config.js ./frontend/

# Copy source
COPY frontend/public ./frontend/public
COPY frontend/src ./frontend/src
COPY frontend/index.html ./frontend/

# Inject API URL at build time (override with --build-arg VITE_API_GATEWAY_URL=...)
ARG VITE_API_GATEWAY_URL=https://api.aura.zae.life/v1
RUN echo "VITE_API_GATEWAY_URL=${VITE_API_GATEWAY_URL}" > ./frontend/.env.production

# Generate protos (writes to frontend/src/lib)
RUN buf generate

WORKDIR /app/frontend

# Build the application
RUN bun run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

RUN apk add --no-cache wget

# Copy built assets to nginx html directory
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Healthy check
HEALTHCHECK --interval=30s --timeout=3s \
  CMD wget -qO- http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
