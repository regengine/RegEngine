#!/bin/bash

###############################################################################
# RegEngine White Paper PDF Export Script
# 
# Purpose: Batch convert Markdown white papers to professionally formatted PDFs
# 
# Requirements:
#   - pandoc (install via: brew install pandoc)
#   - xelatex (install via: brew install --cask mactex)
#   - Inter font (install via: brew tap homebrew/cask-fonts && brew install font-inter)
#
# Usage:
#   ./export_pdf.sh [whitepaper_file.md] [--all]
#   
# Examples:
#   ./export_pdf.sh fsma_whitepaper.md           # Export single white paper
#   ./export_pdf.sh --all                         # Export all white papers
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/pdf"
TEMPLATE="${SCRIPT_DIR}/pdf-template.yaml"

# Create output directory if it doesn't exist
mkdir -p "${OUTPUT_DIR}"

###############################################################################
# Function: check_dependencies
# Verify required tools are installed
###############################################################################
check_dependencies() {
    echo -e "${YELLOW}Checking dependencies...${NC}"
    
    if ! command -v pandoc &> /dev/null; then
        echo -e "${RED}Error: pandoc not found${NC}"
        echo "Install with: brew install pandoc"
        exit 1
    fi
    
    if ! command -v xelatex &> /dev/null; then
        echo -e "${RED}Error: xelatex not found${NC}"
        echo "Install MacTeX with: brew install --cask mactex"
        exit 1
    fi
    
    echo -e "${GREEN}✓ All dependencies found${NC}"
}

###############################################################################
# Function: export_pdf
# Convert a single Markdown white paper to PDF
# 
# Args:
#   $1: Input Markdown file path
###############################################################################
export_pdf() {
    local input_file="$1"
    local filename=$(basename "$input_file" .md)
    local output_file="${OUTPUT_DIR}/${filename}.pdf"
    
    # Extract metadata from filename
    local vertical=$(echo "$filename" | cut -d'_' -f1)
    local vertical_title=$(echo "$vertical" | sed 's/.*/\u&/')  # Capitalize first letter
    
    echo -e "${YELLOW}Exporting: ${filename}.md${NC}"
    
    # Run Pandoc with template and metadata
    pandoc "$input_file" \
        --defaults="${TEMPLATE}" \
        --metadata title="RegEngine for ${vertical_title^} Compliance" \
        --metadata subtitle="Competitive Positioning White Paper" \
        --metadata author="RegEngine" \
        --metadata date="January 2026" \
        -o "$output_file" \
        2>&1 | grep -v "Missing character" || true  # Suppress font warnings
    
    if [ -f "$output_file" ]; then
        local filesize=$(du -h "$output_file" | cut -f1)
        echo -e "${GREEN}✓ Created: ${output_file} (${filesize})${NC}"
    else
        echo -e "${RED}✗ Failed to create: ${output_file}${NC}"
        return 1
    fi
}

###############################################################################
# Function: export_all
# Export all white paper Markdown files in the current directory
###############################################################################
export_all() {
    echo -e "${YELLOW}Exporting all white papers...${NC}\n"
    
    local count=0
    local success=0
    
    for file in "${SCRIPT_DIR}"/*_whitepaper.md; do
        if [ -f "$file" ]; then
            ((count++))
            if export_pdf "$file"; then
                ((success++))
            fi
            echo ""  # Blank line between exports
        fi
    done
    
    echo -e "${GREEN}======================================${NC}"
    echo -e "${GREEN}Export Summary${NC}"
    echo -e "${GREEN}======================================${NC}"
    echo -e "Total white papers: ${count}"
    echo -e "Successfully exported: ${success}"
    echo -e "Failed: $((count - success))"
    echo -e "Output directory: ${OUTPUT_DIR}"
    echo -e "${GREEN}======================================${NC}"
}

###############################################################################
# Main Script Logic
###############################################################################

# Check dependencies first
check_dependencies
echo ""

# Parse arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 [whitepaper_file.md] [--all]"
    echo ""
    echo "Examples:"
    echo "  $0 fsma_whitepaper.md           # Export single white paper"
    echo "  $0 --all                         # Export all white papers"
    exit 1
fi

if [ "$1" == "--all" ]; then
    export_all
else
    # Export single file
    if [ ! -f "$1" ]; then
        echo -e "${RED}Error: File not found: $1${NC}"
        exit 1
    fi
    export_pdf "$1"
fi

echo -e "\n${GREEN}✓ PDF export complete!${NC}"
