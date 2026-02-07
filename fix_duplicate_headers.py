#!/usr/bin/env python3
"""
Script to remove duplicate MarketingHeader and MarketingFooter from page.tsx files.
The root layout already provides these components, so individual pages should not include them.
"""

import os
import re
from pathlib import Path

def remove_duplicate_headers(file_path):
    """Remove MarketingHeader and MarketingFooter imports and JSX from a page.tsx file."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # Remove the import for MarketingHeader (with or without MarketingFooter)
    content = re.sub(
        r"import \{ MarketingHeader(, MarketingFooter)? \} from '@/components/layout/(marketing-header|marketing-footer)';\n?",
        '',
        content
    )
    
    # Remove standalone MarketingFooter import if it exists
    content = re.sub(
        r"import \{ MarketingFooter \} from '@/components/layout/marketing-footer';\n?",
        '',
        content
    )
    
    # Remove <MarketingHeader /> with optional whitespace
    content = re.sub(r'\s*<MarketingHeader />\n?', '', content)
    
    # Remove <MarketingFooter /> with optional whitespace  
    content = re.sub(r'\s*<MarketingFooter />\n?', '', content)
    
    # Remove empty fragment wrappers that may have been left behind
    # Pattern: <>...</> where the only content between is whitespace and other JSX
    # We'll clean up <>...content...</> -> content if it's the only thing in return
    
    # Check if content changed
    if content != original_content:
        with open(file_path, 'w') as f:
            f.write(content)
        return True
    return False

def main():
    # Find all page.tsx files in the frontend/src/app directory
    frontend_dir = Path('/Users/christophersellers/Desktop/RegEngine/frontend/src/app')
    page_files = list(frontend_dir.rglob('page.tsx'))
    
    # Exclude the root layout.tsx (it should keep the headers)
    page_files = [f for f in page_files if 'layout.tsx' not in str(f)]
    
    modified_count = 0
    for page_file in page_files:
        if remove_duplicate_headers(page_file):
            print(f"✓ Fixed: {page_file.relative_to(frontend_dir)}")
            modified_count += 1
    
    print(f"\n✅ Modified {modified_count} files")
    print(f"📝 Total files checked: {len(page_files)}")

if __name__ == '__main__':
    main()
