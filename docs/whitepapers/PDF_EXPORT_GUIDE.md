# PDF Export Workflow Guide

Use this guide only for FSMA-related white papers or PDF collateral that remains in scope for the current repository.

The underlying workflow still uses:

- `export_pdf.sh`
- `pdf-template.yaml`
- Pandoc
- XeLaTeX

Non-FSMA example filenames and vertical-specific export instructions were removed with the archived white papers.

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
