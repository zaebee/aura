# Aura Frontend

A lightning-fast, tiny containerized React application built with Vite and TypeScript, following the ATCG-M architectural pattern.

## 🚀 Overview

The Aura Frontend serves as the user interface for the Aura Agent system. It has been migrated from Next.js to a pure client-side Vite + React setup to achieve minimal image size (<25MB) and maximum performance.

## 🧬 ATCG-M Architecture

This project follows the Hive's internal structure:

- **Aggregator (`src/hive/aggregator/`)**: Logic for fetching Hive State and Search results.
- **Transformer (`src/hive/transformer/`)**: The JIT (Just-In-Time) UI engine that transforms backend requests into dynamic React components.
- **Connector (`src/hive/connector/`)**: API calling logic and Agent Wallet management.
- **Membrane (`src/hive/membrane/`)**: Input validation and schema checking.

## 🛠️ Development

### Prerequisites

- [Bun](https://bun.sh/) (preferred) or Node.js 20+

### Setup

```bash
cd frontend
bun install
```

### Run Development Server

```bash
bun run dev
```

### Build for Production

```bash
bun run build
```

### Linting

```bash
bun run lint
```

### Protocol Synchronization

To regenerate TypeScript stubs from Protobuf definitions:

```bash
bun run gen:proto
```

## 🐳 Docker

The project uses a multi-stage Docker build:
1. **Builder**: Uses `oven/bun:alpine` to build static assets.
2. **Runner**: Uses `nginx:alpine` to serve the `dist/` folder.

Final image size is optimized to be under 25MB.
