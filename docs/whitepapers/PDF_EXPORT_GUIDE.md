# PDF Export Workflow Guide

This guide explains how to generate professional PDFs from RegEngine white paper Markdown files.

---

## Prerequisites

### Required Tools

1. **Pandoc** (document converter)
   ```bash
brew install pandoc
   ```

2. **MacTeX** (LaTeX distribution with XeLaTeX)
   ```bash
   brew install --cask mactex
   ```
   
   After installation, restart your terminal or run:
   ```bash
   eval "$(/usr/libexec/path_helper)"
   ```

3. **Inter Font** (RegEngine brand typography)
   ```bash
   brew tap homebrew/cask-fonts
   brew install font-inter
   ```

### Verify Installation

```bash
pandoc --version      # Should show v2.19+
xelatex --version     # Should show TeX Live 2023+
fc-list | grep Inter  # Should list Inter font variants
```

---

## Quick Start

### Export Single White Paper

```bash
cd /Users/christophersellers/Desktop/RegEngine/docs/whitepapers
./export_pdf.sh finance_sox_whitepaper.md
```

Output: `pdf/finance_sox_whitepaper.pdf`

### Export All White Papers

```bash
./export_pdf.sh --all
```

Output: All `*_whitepaper.md` files → `pdf/*.pdf`

---

## PDF Template Configuration

The [`pdf-template.yaml`](./pdf-template.yaml) file controls PDF styling:

### Brand Colors
- **Primary Blue:** `#0066CC` (links, headings)
- **Dark Text:** `#1a1a1a` (body text)
- **Gray Text:** `#666666` (footers, captions)

### Typography
- **Main Font:** Inter (11pt, 1.15 line spacing)
- **Monospace:** Fira Code (code blocks)

### Layout
- **Page Size:** US Letter (8.5" × 11")
- **Margins:** 1 inch all sides
- **Headers:** Document title (left), "RegEngine" (right)
- **Footers:** Page number (center)

### Features
- Numbered sections with table of contents (2-level depth)
- Clickable internal links and URLs
- Professional table styling with booktabs
- Callout boxes with left blue border
- Code block syntax highlighting

---

## Customization

### Override Metadata per White Paper

You can customize PDFs without editing the template:

```bash
pandoc finance_sox_whitepaper.md \
  --defaults=pdf-template.yaml \
  --metadata title="Custom Title" \
  --metadata subtitle="Custom Subtitle" \
  --metadata date="February 2026" \
  -o custom_output.pdf
```

### Add Cover Logo

1. Place logo in `assets/regengine-logo.png`
2. Edit `pdf-template.yaml` header-includes section:

```latex
\newcommand{\makecover}{
  \begin{titlepage}
    \centering
    \includegraphics[width=0.3\textwidth]{assets/regengine-logo.png}\\[2cm]
    {\Huge\bfseries\color{regdark}\thetitle\par}
    ...
  \end{titlepage}
}
```

### Change Colors

Edit `pdf-template.yaml` color definitions:

```latex
\definecolor{regblue}{HTML}{0066CC}    % Change to your brand blue
\definecolor{regdark}{HTML}{1a1a1a}    % Change to your dark text
\definecolor{reggray}{HTML}{666666}    % Change to your gray
```

---

## Troubleshooting

### Error: "pandoc: command not found"

**Solution:** Install Pandoc:
```bash
brew install pandoc
```

### Error: "xelatex: command not found"

**Solution:** Install MacTeX and restart terminal:
```bash
brew install --cask mactex
eval "$(/usr/libexec/path_helper)"
```

### Error: "! Font 'Inter' in not loadable"

**Solution:** Install Inter font:
```bash
brew tap homebrew/cask-fonts
brew install font-inter
```

Verify installation:
```bash
fc-list | grep Inter
```

### Warning: "Missing character: There is no X in font..."

**Cause:** Unicode characters not in Inter font (rare).

**Solution:** These warnings can be safely ignored; characters will render with fallback fonts. To suppress warnings:

```bash
./export_pdf.sh finance_sox_whitepaper.md 2>&1 | grep -v "Missing character"
```

### PDF Output is Blank or Corrupted

**Cause:** LaTeX compilation errors.

**Solution:** Run Pandoc manually to see full error output:

```bash
pandoc finance_sox_whitepaper.md \
  --defaults=pdf-template.yaml \
  -o test.pdf \
  --verbose
```

Check for:
- Unescaped special characters (`$`, `%`, `&`, `#` in text)
- Malformed tables (inconsistent column counts)
- Invalid LaTeX in code blocks

---

## Best Practices

### Before Export

1. **Run QA checklist** on Markdown source
2. **Validate tables** (consistent columns, proper headers)
3. **Test internal links** (section references)
4. **Check special characters** (escape `$`, `%`, `#`, `&` if not in code blocks)

### After Export

1. **Visual review** (page breaks, table wrapping)
2. **Link testing** (table of contents, URLs)
3. **Print preview** (margin alignment, header/footer placement)
4. **File size check** (typical: 500KB-2MB for 30-40 page white paper)

### Distribution

- **Web:** Compress PDFs with Adobe Acrobat or similar (target: <1MB)
- **Email:** Use PDF/A format for long-term archiving
- **Print:** Ensure 300 DPI minimum for graphics

---

## Advanced: Batch Processing with Custom Metadata

Create a script to export white papers with vertical-specific metadata:

```bash
#!/bin/bash

declare -A VERTICALS=(
  ["finance"]="Finance & Banking"
  ["healthcare"]="Healthcare Providers"
  ["energy"]="Electric Utilities"
  ["nuclear"]="Nuclear Power Generation"
)

for vertical in "${!VERTICALS[@]}"; do
  pandoc "${vertical}_*_whitepaper.md" \
    --defaults=pdf-template.yaml \
    --metadata title="RegEngine for ${VERTICALS[$vertical]}" \
    -o "pdf/${vertical}_whitepaper.pdf"
done
```

---

## Appendix: Template Structure

### LaTeX Packages Used

| Package        | Purpose                              |
| -------------- | ------------------------------------ |
| fancyhdr       | Custom headers/footers               |
| xcolor         | Brand color definitions              |
| hyperref       | Clickable links and TOC              |
| longtable      | Multi-page table support             |
| booktabs       | Professional table rules             |
| titlesec       | Custom section heading styles        |
| mdframed       | Callout box borders                  |
| listings       | Code block syntax highlighting       |

### YAML Front Matter Override

You can override template settings in individual Markdown files:

```yaml
---
title: "Custom Finance White Paper"
subtitle: "Internal Review Draft"
author: "RegEngine Product Team"
date: "Draft - Do Not Distribute"
geometry:
  - margin=0.75in
fontsize: 10pt
---

# Document content starts here...
```

---

## Version Control

**Guide Version:** 1.0
**Last Updated:** January 30, 2026
**Template Version:** 1.0
**Maintained by:** RegEngine Marketing Operations
