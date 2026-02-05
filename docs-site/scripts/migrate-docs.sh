#!/bin/bash
# Migration script for existing documentation to Docusaurus
# Copies and adjusts markdown files from docs/ to docs-site/docs/

set -e

echo "🚀 Starting documentation migration..."

# Get the project root directory
PROJECT_ROOT="/home/zaebee/projects/aura"
DOCS_SRC="$PROJECT_ROOT/docs"
DOCS_DEST="$PROJECT_ROOT/docs-site/docs"

# Create destination directories if they don't exist
mkdir -p "$DOCS_DEST/visual/hive"
mkdir -p "$DOCS_DEST/visual/components"
mkdir -p "$DOCS_DEST/visual/pipelines"
mkdir -p "$DOCS_DEST/api"
mkdir -p "$DOCS_DEST/protocols"
mkdir -p "$DOCS_DEST/architecture"

# Copy visual documentation if it exists
if [ -d "$DOCS_SRC/visual" ]; then
  echo "📁 Copying visual documentation..."

  # Copy root visual docs
  if [ -f "$DOCS_SRC/visual/index.md" ]; then
    cp "$DOCS_SRC/visual/index.md" "$DOCS_DEST/visual/"
  fi

  if [ -f "$DOCS_SRC/visual/metabolism.md" ]; then
    cp "$DOCS_SRC/visual/metabolism.md" "$DOCS_DEST/visual/"
  fi

  # Copy hive subdirectory
  if [ -d "$DOCS_SRC/visual/hive" ]; then
    cp -r "$DOCS_SRC/visual/hive/"*.md "$DOCS_DEST/visual/hive/" 2>/dev/null || true
  fi

  # Copy components subdirectory
  if [ -d "$DOCS_SRC/visual/components" ]; then
    cp -r "$DOCS_SRC/visual/components/"*.md "$DOCS_DEST/visual/components/" 2>/dev/null || true
  fi

  # Copy pipelines subdirectory
  if [ -d "$DOCS_SRC/visual/pipelines" ]; then
    cp -r "$DOCS_SRC/visual/pipelines/"*.md "$DOCS_DEST/visual/pipelines/" 2>/dev/null || true
  fi
fi

# Copy foundation docs
if [ -f "$DOCS_SRC/FOUNDATION.md" ]; then
  echo "📄 Copying FOUNDATION.md..."
  cp "$DOCS_SRC/FOUNDATION.md" "$DOCS_DEST/architecture/foundation.md"
fi

# Copy arch_brain.json to static directory
if [ -f "$DOCS_SRC/arch_brain.json" ]; then
  echo "🧠 Copying arch_brain.json..."
  cp "$DOCS_SRC/arch_brain.json" "$PROJECT_ROOT/docs-site/static/arch/"
fi

# Adjust internal links (Markdown → Docusaurus format)
echo "🔗 Adjusting internal links..."

# Fix relative markdown links: [Link](../foo.md) → [Link](/docs/foo)
find "$DOCS_DEST" -name "*.md" -type f -exec sed -i 's|\](\.\.\/|](/docs/|g' {} \;

# Remove .md extensions from links: [Link](/docs/foo.md) → [Link](/docs/foo)
find "$DOCS_DEST" -name "*.md" -type f -exec sed -i 's|\.md)|)|g' {} \;

# Fix same-directory links: [Link](./foo.md) → [Link](foo)
find "$DOCS_DEST" -name "*.md" -type f -exec sed -i 's|\](\.\/\([^)]*\)\.md)|\](\1)|g' {} \;

echo "✅ Documentation migration complete!"
echo ""
echo "📊 Migration summary:"
echo "  Source: $DOCS_SRC"
echo "  Destination: $DOCS_DEST"
echo ""
echo "Next steps:"
echo "  1. Review migrated files in docs-site/docs/"
echo "  2. Run 'cd docs-site && bun start' to preview"
echo "  3. Update sidebars.ts with the new structure"
