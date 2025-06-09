# MarkdownStream Theme System

The MarkdownStream React component now features a powerful dynamic theme loading system that supports both local embedded themes and CDN-loaded themes from highlight.js.

## Features

- 🎨 **Dynamic Theme Loading**: Automatically loads highlight.js themes at runtime
- 📦 **Local Fallbacks**: Embedded `atom-one-light` and `atom-one-dark` themes
- 🌐 **CDN Support**: Loads themes from highlight.js CDN with automatic fallback
- 🔄 **Auto Theme Detection**: Switches between light/dark based on system preferences
- ⚙️ **Configurable**: Set custom themes via component props
- 🧹 **Automatic Cleanup**: Removes old stylesheets when switching themes
- 🛡️ **Error Handling**: Graceful fallback if themes fail to load

## Basic Usage

```tsx
import { MarkdownStream } from './components/MarkdownStream'

// Default usage with embedded themes
<MarkdownStream 
  content="# Hello World\n\n```javascript\nconsole.log('Hello!');\n```"
  contentType="markdown"
  streaming={true}
/>
```

## Theme Configuration

### Custom Themes

```tsx
<MarkdownStream 
  content={content}
  contentType="markdown"
  lightTheme="github"           // Use GitHub theme for light mode
  darkTheme="monokai"          // Use Monokai theme for dark mode
  useLocalThemes={false}       // Load from CDN
/>
```

### Local Embedded Themes

```tsx
<MarkdownStream 
  content={content}
  contentType="markdown"
  lightTheme="atom-one-light"  // Uses embedded theme
  darkTheme="atom-one-dark"    // Uses embedded theme  
  useLocalThemes={true}        // Prefer local themes
/>
```

## Props Reference

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `lightTheme` | `string` | `"atom-one-light"` | Theme name for light mode |
| `darkTheme` | `string` | `"atom-one-dark"` | Theme name for dark mode |
| `useLocalThemes` | `boolean` | `true` | Prefer embedded themes over CDN |

## Available Themes

### Embedded Themes (Local)
- `atom-one-light` - Clean light theme with good contrast
- `atom-one-dark` - Dark theme with syntax highlighting

### Popular CDN Themes
- **Light Themes**: `github`, `vs`, `solarized-light`, `tomorrow`, `rainbow`
- **Dark Themes**: `github-dark`, `vs2015`, `monokai`, `solarized-dark`, `tomorrow-night`, `dracula`, `nord`, `zenburn`

## Theme Detection Logic

The component automatically detects the appropriate theme based on:

1. **System Preference**: `(prefers-color-scheme: dark)`
2. **Bootstrap Theme**: `data-bs-theme="dark"` attribute
3. **CSS Class**: `.dark-theme` class on document body

```javascript
const isDarkMode = 
  window.matchMedia("(prefers-color-scheme: dark)").matches ||
  document.documentElement.getAttribute("data-bs-theme") === "dark" ||
  document.body.classList.contains("dark-theme")
```

## CDN Theme Loading

When `useLocalThemes={false}`, themes are loaded from:
```
https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/{theme-name}.min.css
```

## Error Handling & Fallbacks

The system includes robust error handling:

1. **CDN Failure**: Falls back to embedded themes if CDN is unavailable
2. **Invalid Theme**: Uses closest match (light themes fall back to `atom-one-light`, dark to `atom-one-dark`)
3. **Network Issues**: Gracefully degrades to embedded themes
4. **Console Warnings**: Logs helpful messages for debugging

## Examples

### Corporate Theme Setup
```tsx
// Use corporate-approved themes with local fallbacks
<MarkdownStream 
  content={content}
  lightTheme="vs"              // Visual Studio light
  darkTheme="vs2015"           // Visual Studio dark
  useLocalThemes={false}       // Load from CDN
/>
```

### Offline-First Setup
```tsx
// Ensure themes work offline
<MarkdownStream 
  content={content}
  lightTheme="atom-one-light"  // Embedded theme
  darkTheme="atom-one-dark"    // Embedded theme
  useLocalThemes={true}        // Always use local
/>
```

### Dynamic Theme Switching
```tsx
const [currentTheme, setCurrentTheme] = useState("github")

// Programmatically change themes
<MarkdownStream 
  content={content}
  lightTheme={currentTheme}
  darkTheme={currentTheme + "-dark"}
  useLocalThemes={false}
/>
```

## Migration from Old System

### Before (Hardcoded CSS)
```tsx
// Old system had hardcoded CSS embedded in the component
<MarkdownStream content={content} />
```

### After (Dynamic Themes)
```tsx
// New system with configurable themes
<MarkdownStream 
  content={content}
  lightTheme="atom-one-light"
  darkTheme="atom-one-dark"
  useLocalThemes={true}
/>
```

## Performance Considerations

- **Lazy Loading**: Themes are only loaded when needed
- **Caching**: Browser caches CDN themes automatically
- **Cleanup**: Old stylesheets are removed to prevent conflicts
- **Throttling**: Theme switches are debounced to prevent rapid changes

## Browser Support

- **Modern Browsers**: Full support for dynamic CSS loading
- **Legacy Browsers**: Falls back to embedded themes
- **Offline**: Works with embedded themes when no network available

## Troubleshooting

### Theme Not Loading
1. Check browser console for error messages
2. Verify theme name spelling
3. Test with `useLocalThemes={true}` to use embedded themes
4. Check network connectivity for CDN themes

### Theme Switching Issues
1. Ensure system theme detection is working
2. Check for conflicting CSS rules
3. Verify theme names are valid highlight.js themes

### Performance Issues
1. Use `useLocalThemes={true}` to avoid network requests
2. Choose fewer theme variants
3. Check for CSS conflicts with other components

## Best Practices

1. **Use Local Themes for Reliability**: Set `useLocalThemes={true}` for critical applications
2. **Test Theme Combinations**: Verify both light and dark themes look good
3. **Handle Theme Changes**: Test rapid theme switching doesn't break layout
4. **Consider Network**: Use CDN themes only when network is reliable
5. **Fallback Strategy**: Always have embedded themes as fallback options
