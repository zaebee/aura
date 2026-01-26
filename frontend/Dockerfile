# Dockerfile for Aura Frontend
# Build stage
FROM oven/bun AS builder

WORKDIR /app

# Install dependencies
COPY package.json ./
COPY bun.lock ./
RUN bun install

# Copy source files
COPY . .

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

# Install only production dependencies
RUN bun install --production

# Environment variables
ENV NODE_ENV production
ENV PORT 3000

# Expose port
EXPOSE 3000

# Start the application
CMD ["bun", "start"]
