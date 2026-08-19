# Aura Hive Documentation Site

Static documentation site built with [Docusaurus](https://docusaurus.io/) featuring interactive React components and auto-generated API documentation.

## Quick Start

```bash
# Install dependencies
bun install

# Start development server
bun start

# Build for production
bun run build

# Serve production build locally
bun run serve
```

The site will open at `http://localhost:3000/aura/` (note the `/aura/` base path for GitHub Pages).

## Project Structure

```
docs-site/
├── docs/                          # Markdown documentation
│   ├── architecture/              # System architecture docs
│   ├── protocols/                 # ATCG-M protocol implementations
│   ├── visual/                    # Visual guides with Mermaid diagrams
│   ├── api/                       # Auto-generated API reference
│   └── interactive/               # Interactive component pages
├── src/
│   ├── components/                # React components (future)
│   │   ├── ProtocolExplorer.tsx  # (Planned) ATCG-M browser
│   │   ├── NegotiationSim.tsx    # (Planned) Metabolism simulator
│   │   └── ProtobufBrowser.tsx   # (Planned) Type explorer
│   ├── css/
│   │   └── custom.css             # Hive-branded cyberpunk styling
│   └── pages/                     # Custom pages
├── static/                        # Static assets
│   └── arch/                      # Architecture data (arch_brain.json)
├── scripts/
│   ├── migrate-docs.sh            # Migration script from docs/
│   └── generate-proto-docs.sh     # Protobuf → Markdown generator
├── docusaurus.config.ts           # Docusaurus configuration
├── sidebars.ts                    # Navigation structure
└── package.json                   # Dependencies
```

## Features

### 1. Migrated Documentation
All existing visual guides and architecture docs have been migrated from `docs/visual/` with:
- Mermaid diagram support (renders natively)
- Adjusted internal links for Docusaurus routing
- Organized sidebar navigation

### 2. Auto-Generated API Docs
Protobuf schemas are automatically converted to Markdown documentation:

```bash
# Generate API docs from .proto files
bun run gen:proto-docs
```

This runs before every build (via `prebuild` script).

### 3. Hive Brand Styling
Custom CSS in `src/css/custom.css` applies cyberpunk colors:
- **Primary**: `#00f2ff` (cyberpunk-blue)
- **Accent**: `#bc13fe` (cyberpunk-purple)
- **Dark mode** by default
- Protocol badges styled by type (A/T/C/G/M)

### 4. Interactive Components (Planned)
React components will import UI from `../frontend/src/components/ui/`:
- `ProtocolExplorer`: Browse ATCG-M implementations
- `NegotiationSim`: Step-through metabolism simulator
- `ProtobufBrowser`: Interactive type explorer

TypeScript paths configured in `tsconfig.json`:
```typescript
"paths": {
  "@frontend/*": ["../frontend/src/*"],
  "@ui/*": ["../frontend/src/components/ui/*"]
}
```

## Scripts

| Command | Description |
|---------|-------------|
| `bun start` | Start dev server with hot reload |
| `bun run build` | Build production site to `build/` |
| `bun run serve` | Serve production build locally |
| `bun run gen:proto-docs` | Generate API docs from Protobuf |
| `bun run clear` | Clear Docusaurus cache |
| `bun run typecheck` | Run TypeScript type checking |

## Deployment

The site deploys automatically to GitHub Pages via `.github/workflows/docs-deploy.yaml`:

1. **Trigger**: Push to `main` branch with changes to `docs/`, `docs-site/`, or `proto/`
2. **Build**: Installs deps, generates proto docs, builds Docusaurus
3. **Deploy**: Publishes to `gh-pages` branch
4. **URL**: `https://zaebee.github.io/aura/`

### Manual Deploy

```bash
# Build site
bun run build

# Deploy to GitHub Pages (requires GH_TOKEN)
GIT_USER=zaebee USE_SSH=true bun run deploy
```

## Configuration

### docusaurus.config.ts
Main configuration file:
- Site metadata (title, tagline, URL)
- GitHub Pages deployment settings
- Navbar and footer structure
- Theme configuration (dark mode, colors)
- Plugin configuration (Mermaid, TypeDoc)

### sidebars.ts
Navigation structure:
- Architecture guides
- Protocol implementations
- Visual diagrams
- API reference
- Interactive components

### custom.css
Hive brand styling:
- CSS variables for colors
- Protocol badge styles
- Card and component themes
- Mermaid diagram styling

## Migration from docs/

The `scripts/migrate-docs.sh` script handles:
- Copying markdown files from `docs/visual/` to `docs-site/docs/visual/`
- Copying `arch_brain.json` to `static/arch/`
- Adjusting internal links for Docusaurus format
- Creating necessary directories

Re-run if you add new docs to the original `docs/` folder.

## Protobuf Documentation

Auto-generated from `.proto` files using `protoc-gen-doc`:

**Requirements**:
- `protoc` (Protocol Buffers compiler)
- `protoc-gen-doc` (Go package)

**Install**:
```bash
# Install protoc (Linux)
curl -LO "https://github.com/protocolbuffers/protobuf/releases/download/v25.1/protoc-25.1-linux-x86_64.zip"
unzip protoc-25.1-linux-x86_64.zip -d $HOME/.local

# Install protoc-gen-doc
go install github.com/pseudomuto/protoc-gen-doc/cmd/protoc-gen-doc@latest
```

**Generate**:
```bash
bun run gen:proto-docs
```

Generated docs appear in `docs/api/`:
- `dna-reference.md` (from `proto/aura/dna/v1/dna.proto`)
- `negotiation-reference.md` (from `proto/aura/negotiation/v1/negotiation.proto`)

## Adding New Documentation

### 1. Create Markdown File
```bash
# Create new doc
echo "# My New Doc" > docs/my-category/my-doc.md
```

### 2. Add to Sidebar
Edit `sidebars.ts`:
```typescript
{
  type: 'category',
  label: 'My Category',
  items: ['my-category/my-doc'],
}
```

### 3. Preview
```bash
bun start
```

Navigate to `http://localhost:3000/aura/docs/my-category/my-doc`

## Troubleshooting

### Build Errors

**"Module not found"**:
- Clear Docusaurus cache: `bun run clear`
- Reinstall dependencies: `rm -rf node_modules && bun install`

**Broken links**:
- Check internal links use `/docs/` prefix (not `../`)
- Remove `.md` extensions from links

**Mermaid diagrams not rendering**:
- Ensure `@docusaurus/theme-mermaid` is installed
- Check `markdown.mermaid: true` in config
- Verify Mermaid syntax is valid

### Proto Doc Generation

**"protoc not found"**:
- Install protoc (see requirements above)
- Add to PATH: `export PATH="$HOME/.local/bin:$PATH"`

**"protoc-gen-doc not found"**:
- Install Go: `https://go.dev/doc/install`
- Run: `go install github.com/pseudomuto/protoc-gen-doc/cmd/protoc-gen-doc@latest`
- Add Go bin to PATH: `export PATH="$(go env GOPATH)/bin:$PATH"`

## Resources

- [Docusaurus Documentation](https://docusaurus.io/)
- [Mermaid Syntax](https://mermaid.js.org/)
- [Protobuf Style Guide](https://protobuf.dev/programming-guides/style/)
- [GitHub Pages Setup](https://docs.github.com/en/pages)

---

*For the glory of the Hive.* 🐝
