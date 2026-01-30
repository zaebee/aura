# Dockerfile for Aura Frontend
# Build stage
FROM oven/bun AS builder

WORKDIR /app

# Install dependencies
COPY frontend/package.json frontend/bun.lock ./
RUN bun install

# Copy configuration files
COPY frontend/next.config.js frontend/tailwind.config.ts frontend/tsconfig.json ./
COPY frontend/postcss.config.mjs frontend/eslint.config.mjs frontend/env.d.ts ./
COPY frontend/.env.production ./

# Copy source files
COPY frontend/src ./src
COPY frontend/public ./public

# Build the application
RUN bun run build

# Production stage
FROM oven/bun AS runner

WORKDIR /app

# Copy built files from builder
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/bun.lock ./bun.lock
COPY --from=builder /app/next.config.js ./next.config.js
COPY --from=builder /app/.env.production ./.env.production

# Install only production dependencies
RUN bun install --production

# Environment variables
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Expose port
EXPOSE 3000

# Start the application
CMD ["bun", "start"]
