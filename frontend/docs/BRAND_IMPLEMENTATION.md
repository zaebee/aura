# Aura Brand Implementation Guide

This guide provides specific implementation details for maintaining brand consistency in the Aura frontend codebase.

## 📁 File Structure

```
frontend/
├── docs/
│   ├── BRAND_GUIDELINES.md      # Comprehensive brand guidelines
│   └── BRAND_IMPLEMENTATION.md  # Implementation specifics (this file)
├── tailwind.config.ts           # Tailwind configuration with brand colors
├── src/
│   ├── app/
│   │   └── globals.css          # Global styles and brand utilities
│   └── components/
│       ├── ui/                 # UI component library
│       └── AgentConsole.tsx    # Main application component
```

## 🎨 Color Implementation

### Tailwind Configuration

All brand colors are defined in `tailwind.config.ts`:

```typescript
colors: {
  // Primary Brand Colors
  'cyberpunk-blue': '#00f2ff',
  'cyberpunk-purple': '#a855f7',
  'cyberpunk-pink': '#ec4899',
  
  // Neutral Colors
  'dark-bg': '#0a0a0a',
  'card-bg': '#1a1a1a',
  'gray-800': '#1f1f1f',
  'gray-700': '#373737',
  'gray-600': '#4b4b4b',
  'gray-500': '#6b6b6b',
  'gray-400': '#9ca3af',
  'gray-300': '#d1d5db',
  
  // Semantic Colors
  'success': '#10b981',
  'warning': '#f59e0b',
  'error': '#ef4444',
  'info': '#3b82f6',
}
```

### Usage with Inline Classes

Aura follows Tailwind's utility-first philosophy by using inline classes rather than custom utility classes. This approach:
- Keeps styles explicit and visible in components
- Enables tree-shaking for unused styles
- Makes it easier to customize per-component
- Reduces CSS file size

**Primary CTA Button:**
```jsx
<Button className="bg-cyberpunk-blue hover:bg-cyberpunk-blue/90 text-white font-semibold py-2 px-4 rounded-md transition-all duration-200">
  Submit
</Button>
```

**Secondary Button:**
```jsx
<Button className="bg-cyberpunk-purple hover:bg-cyberpunk-purple/90 text-white font-semibold py-2 px-4 rounded-md transition-all duration-200">
  Cancel
</Button>
```

**Card Component:**
```jsx
<Card className="bg-card-bg border border-gray-700 rounded-lg shadow-card">
  {/* Card content */}
</Card>
```

**Input Field:**
```jsx
<Input className="bg-gray-800 border border-gray-600 text-white rounded-md py-2 px-3 focus:outline-none focus:border-cyberpunk-blue focus:ring-1 focus:ring-cyberpunk-blue" />
```

**Error State:**
```jsx
<Alert className="bg-error/20 border-error">
  <AlertTitle className="text-error h4">Error</AlertTitle>
  <AlertDescription className="body-text">Something went wrong</AlertDescription>
</Alert>
```

## 📐 Typography Implementation

### Font Families

The Inter font family is used as the primary typeface:

```css
@layer base {
  body {
    @apply font-sans; /* Uses Inter font stack */
  }
}
```

### Typography Classes

Semantic typography classes are defined in `globals.css` for consistent text hierarchy:

```css
/* Heading Styles */
h1, .h1 {
  font-size: 3rem;
  line-height: 1.2;
  font-weight: 700;
  color: white;
}
h2, .h2 {
  font-size: 2.25rem;
  line-height: 1.2;
  font-weight: 600;
  color: white;
}
h3, .h3 {
  font-size: 1.875rem;
  line-height: 1.2;
  font-weight: 600;
  color: white;
}
h4, .h4 {
  font-size: 1.5rem;
  line-height: 1.2;
  font-weight: 600;
  color: white;
}

/* Body Text */
p, .body-text {
  font-size: 1rem;
  line-height: 1.5;
  color: #9ca3af;
}
.body-text-sm {
  font-size: 0.875rem;
  line-height: 1.5;
  color: #9ca3af;
}
.caption-text {
  font-size: 0.75rem;
  line-height: 1.4;
  color: #6b6b6b;
}
```

**Note**: These semantic classes use CSS properties directly rather than `@apply` directives due to Tailwind CSS v4 constraints with custom color references.

### Usage Examples

**Main Heading:**
```jsx
<h1 className="h1">Aura Agent Console</h1>
```

**Section Heading:**
```jsx
<h3 className="h3 text-cyberpunk-blue">Search Inventory</h3>
```

**Body Text:**
```jsx
<p className="body-text">Find items to negotiate</p>
```

**Caption:**
```jsx
<span className="caption-text">ID: {item.itemId}</span>
```

## 🎯 Component Styles

### Card Component

Use inline Tailwind classes for consistent card styling:

```jsx
<Card className="bg-card-bg border border-gray-700 rounded-lg shadow-card">
  {/* Card content */}
</Card>
```

This applies:
- Background: `bg-card-bg` (#1a1a1a)
- Border: `border-gray-700` (#373737)
- Border Radius: `rounded-lg` (0.5rem / 8px)
- Shadow: `shadow-card` (subtle card shadow)

### Input Component

Use inline Tailwind classes for consistent input styling:

```jsx
<Input className="bg-gray-800 border border-gray-600 text-white rounded-md py-2 px-3 focus:outline-none focus:border-cyberpunk-blue focus:ring-1 focus:ring-cyberpunk-blue" />
```

This applies:
- Background: `bg-gray-800` (#1f1f1f)
- Border: `border-gray-600` (#4b4b4b)
- Text: `text-white`
- Focus: cyberpunk-blue ring with outline removal

### Button Components

Use inline Tailwind classes for consistent button styling:

```jsx
// Primary button
<Button className="bg-cyberpunk-blue hover:bg-cyberpunk-blue/90 text-white font-semibold py-2 px-4 rounded-md transition-all duration-200">
  Submit
</Button>

// Secondary button
<Button className="bg-cyberpunk-purple hover:bg-cyberpunk-purple/90 text-white font-semibold py-2 px-4 rounded-md transition-all duration-200">
  Cancel
</Button>

// Destructive button
<Button className="bg-error hover:bg-error/90 text-white font-semibold py-2 px-4 rounded-md transition-all duration-200">
  Delete
</Button>
```

## 🎭 Animations & Transitions

### Transitions

Use inline Tailwind classes for consistent transitions:

```jsx
<div className="transition-all duration-200">
  {/* Content with smooth transitions */}
</div>
```

Common transition patterns:
```jsx
// All properties
className="transition-all duration-200"

// Specific properties
className="transition-colors duration-200"
className="transition-transform duration-300"
className="transition-opacity duration-150"
```

### Fade-in Animation

Use the `animate-fade-in` utility class for fade-in effects:

```jsx
<div className="animate-fade-in">
  {/* Content that fades in */}
</div>
```

This animation is defined in `globals.css` using `@keyframes`:

```css
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-fade-in {
  animation: fadeIn 0.3s ease-out forwards;
}
```

## 🌙 Dark Mode Implementation

Aura uses a dark-first approach with Tailwind's dark mode:

```javascript
// tailwind.config.ts
darkMode: 'class',
```

```html
<!-- In your layout -->
<html className="dark">
  <body className="bg-dark-bg text-white">
    {/* Content */}
  </body>
</html>
```

## 📱 Responsive Design

### Breakpoints

Use Tailwind's built-in breakpoints:

```jsx
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
  {/* Responsive grid */}
</div>
```

### Container Sizing

```jsx
<div className="max-w-7xl mx-auto px-4">
  {/* Content with proper max-width and padding */}
</div>
```

## 🔒 Accessibility

### Focus Styles

Global focus styles are defined in `globals.css`:

```css
*:focus {
  outline: none;
  box-shadow: 0 0 0 2px #0a0a0a, 0 0 0 4px #00f2ff;
}
```

This creates a dual-ring focus indicator:
- Inner ring: `dark-bg` (#0a0a0a) - 2px offset
- Outer ring: `cyberpunk-blue` (#00f2ff) - 4px offset

For component-specific focus states, use inline Tailwind classes:

```jsx
<Input className="focus:outline-none focus:border-cyberpunk-blue focus:ring-1 focus:ring-cyberpunk-blue" />
```

### Semantic HTML

Always use semantic HTML elements:

```jsx
// Good
<button onClick={handleClick}>Click me</button>

// Bad
<div onClick={handleClick}>Click me</div>
```

### ARIA Attributes

Use proper ARIA attributes:

```jsx
<button aria-label="Search" aria-disabled={isLoading}>
  <SearchIcon />
</button>
```

## 📋 Component Checklist

### Creating New Components

1. **Color**: Use brand colors from Tailwind config (e.g., `bg-cyberpunk-blue`, `text-gray-400`)
2. **Typography**: Use semantic typography classes (`.h1`, `.h2`, `.body-text`, `.caption-text`)
3. **Spacing**: Use Tailwind's spacing scale (e.g., `p-4`, `space-y-2`, `gap-4`)
4. **Borders**: Use `border-gray-700` for standard borders
5. **Transitions**: Add `transition-all duration-200` for interactive elements
6. **Accessibility**: Ensure proper focus states and ARIA attributes
7. **Responsive**: Test on all breakpoints (use `sm:`, `md:`, `lg:` prefixes)
8. **Dark Mode**: Verify dark mode compatibility

### Component Review

- [ ] Uses brand colors correctly
- [ ] Follows typography guidelines
- [ ] Has proper spacing
- [ ] Includes hover/focus states
- [ ] Is accessible (keyboard, screen reader)
- [ ] Works on mobile devices
- [ ] Supports dark mode
- [ ] Has consistent transitions

## 🔧 Development Workflow

### Adding New Colors

1. Add to `tailwind.config.ts`
2. Document in `BRAND_GUIDELINES.md`
3. Update `BRAND_IMPLEMENTATION.md` with usage examples
4. Test contrast ratios

### Adding New Typography

1. Define in `globals.css`
2. Add to typography table in guidelines
3. Document usage patterns

### Creating New Components

1. Follow existing patterns
2. Use brand utility classes
3. Add to component library if reusable
4. Document component usage

## 🧪 Testing Brand Consistency

### Visual Regression Testing

Use tools like:
- Storybook for component isolation
- Chromatic for visual regression testing
- BrowserStack for cross-browser testing

### Automated Checks

```javascript
// Example: Color contrast check (pseudo-code)
const checkContrast = (foreground, background) => {
  const contrastRatio = calculateContrast(foreground, background);
  if (contrastRatio < 4.5) {
    console.warn(`Low contrast: ${contrastRatio}`);
  }
}
```

## 📝 Common Patterns

### Gradient Backgrounds

Use the `bg-cyberpunk-gradient` utility for gradient backgrounds:

```jsx
<h1 className="bg-cyberpunk-gradient bg-clip-text text-transparent">
  Aura Agent Console
</h1>
```

The gradient is defined in `tailwind.config.ts`:
```typescript
backgroundImage: {
  'cyberpunk-gradient': 'linear-gradient(135deg, #00f2ff 0%, #a855f7 100%)',
}
```

### Status Badges

```jsx
<Badge variant={score > 0.8 ? 'default' : 'secondary'} className="caption-text">
  {score}%
</Badge>
```

### Loading States

```jsx
<Button disabled={isLoading} className="bg-cyberpunk-blue hover:bg-cyberpunk-blue/90 text-white font-semibold py-2 px-4 rounded-md transition-all duration-200">
  {isLoading ? 'Processing...' : 'Submit'}
</Button>
```

### Interactive Cards

```jsx
<Card
  className="bg-card-bg border border-gray-700 rounded-lg shadow-card cursor-pointer hover:border-cyberpunk-blue transition-all duration-200"
  onClick={handleClick}
>
  {/* Card content */}
</Card>
```

## 🔗 Integration with Design Tools

### Figma to Code

1. Use Figma's Tailwind plugin
2. Map Figma styles to Tailwind classes
3. Export assets with proper naming
4. Use Figma variables for brand colors

### Design Token Management

```json
// Example design tokens (conceptual)
{
  "colors": {
    "primary": {
      "value": "#00f2ff",
      "name": "cyberpunk-blue"
    }
  },
  "typography": {
    "h1": {
      "fontSize": "3rem",
      "fontWeight": "700",
      "lineHeight": "1.2"
    }
  }
}
```

## 📋 Maintenance

### Updating Brand Guidelines

1. Update `BRAND_GUIDELINES.md`
2. Update `BRAND_IMPLEMENTATION.md`
3. Update Tailwind config
4. Update global CSS
5. Create migration guide if needed
6. Update all components

### Versioning

Follow semantic versioning for brand changes:
- **Patch**: Minor tweaks, bug fixes
- **Minor**: New components, non-breaking changes
- **Major**: Complete redesign, breaking changes

## 🤝 Contributing

### Reporting Brand Issues

1. Open GitHub issue
2. Tag with `brand` label
3. Include screenshots
4. Specify location
5. Suggest fix if possible

### Brand Review Process

1. Design team review
2. Engineering team implementation
3. QA testing
4. Stakeholder approval
5. Documentation update

---

*© 2024 Aura Platform. All rights reserved.*
