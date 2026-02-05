#!/bin/bash
# Generate Markdown API documentation from Protobuf files
# Requires protoc and protoc-gen-doc to be installed

set -e

echo "🔧 Generating Protobuf documentation..."

# Get the project root directory
PROJECT_ROOT="/home/zaebee/projects/aura"
PROTO_DIR="$PROJECT_ROOT/proto"
DOCS_OUTPUT="$PROJECT_ROOT/docs-site/docs/api"

# Check if protoc is installed
if ! command -v protoc &> /dev/null; then
    echo "⚠️  protoc not found. Skipping proto doc generation."
    echo "   Install from: https://grpc.io/docs/protoc-installation/"
    exit 0
fi

# Check if protoc-gen-doc is installed
if ! command -v protoc-gen-doc &> /dev/null; then
    echo "⚠️  protoc-gen-doc not found. Attempting to install..."

    if command -v go &> /dev/null; then
        echo "   Installing protoc-gen-doc via go..."
        go install github.com/pseudomuto/protoc-gen-doc/cmd/protoc-gen-doc@latest
        export PATH="$(go env GOPATH)/bin:$PATH"
    else
        echo "   Go not found. Skipping proto doc generation."
        echo "   Install Go and run: go install github.com/pseudomuto/protoc-gen-doc/cmd/protoc-gen-doc@latest"
        exit 0
    fi
fi

# Create output directory
mkdir -p "$DOCS_OUTPUT"

# Check if proto files exist
if [ ! -d "$PROTO_DIR" ]; then
    echo "⚠️  Proto directory not found at $PROTO_DIR"
    echo "   Skipping proto doc generation."
    exit 0
fi

# Generate documentation for dna.proto if it exists
if [ -f "$PROTO_DIR/aura/dna/v1/dna.proto" ]; then
    echo "📄 Generating docs for dna.proto..."

    protoc \
        --doc_out="$DOCS_OUTPUT" \
        --doc_opt=markdown,dna-reference.md \
        --proto_path="$PROTO_DIR" \
        "$PROTO_DIR/aura/dna/v1/dna.proto" \
        2>&1 || echo "   ⚠️  Failed to generate dna.proto docs"

    # Add frontmatter if file was generated
    if [ -f "$DOCS_OUTPUT/dna-reference.md" ]; then
        echo "   Adding frontmatter to dna-reference.md..."
        cat > "$DOCS_OUTPUT/dna-reference.md.tmp" << 'FRONTMATTER'
---
sidebar_position: 1
---

# DNA Type Reference

:::info Auto-Generated
This documentation is automatically generated from `proto/aura/dna/v1/dna.proto`.
Run \`bun run gen:proto-docs\` to regenerate.
:::

FRONTMATTER
        cat "$DOCS_OUTPUT/dna-reference.md" >> "$DOCS_OUTPUT/dna-reference.md.tmp"
        mv "$DOCS_OUTPUT/dna-reference.md.tmp" "$DOCS_OUTPUT/dna-reference.md"
    fi
else
    echo "⚠️  dna.proto not found at $PROTO_DIR/aura/dna/v1/dna.proto"
fi

# Generate documentation for negotiation.proto if it exists
if [ -f "$PROTO_DIR/aura/negotiation/v1/negotiation.proto" ]; then
    echo "📄 Generating docs for negotiation.proto..."

    protoc \
        --doc_out="$DOCS_OUTPUT" \
        --doc_opt=markdown,negotiation-reference.md \
        --proto_path="$PROTO_DIR" \
        "$PROTO_DIR/aura/negotiation/v1/negotiation.proto" \
        2>&1 || echo "   ⚠️  Failed to generate negotiation.proto docs"

    # Add frontmatter if file was generated
    if [ -f "$DOCS_OUTPUT/negotiation-reference.md" ]; then
        echo "   Adding frontmatter to negotiation-reference.md..."
        cat > "$DOCS_OUTPUT/negotiation-reference.md.tmp" << 'FRONTMATTER'
---
sidebar_position: 2
---

# Negotiation API Reference

:::info Auto-Generated
This documentation is automatically generated from `proto/aura/negotiation/v1/negotiation.proto`.
Run \`bun run gen:proto-docs\` to regenerate.
:::

FRONTMATTER
        cat "$DOCS_OUTPUT/negotiation-reference.md" >> "$DOCS_OUTPUT/negotiation-reference.md.tmp"
        mv "$DOCS_OUTPUT/negotiation-reference.md.tmp" "$DOCS_OUTPUT/negotiation-reference.md"
    fi
else
    echo "⚠️  negotiation.proto not found at $PROTO_DIR/aura/negotiation/v1/negotiation.proto"
fi

echo "✅ Protobuf documentation generation complete!"
echo ""
echo "📊 Generated files:"
ls -lh "$DOCS_OUTPUT"/*.md 2>/dev/null || echo "   No markdown files generated"
