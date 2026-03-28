/**
 * Production Budget Parser
 * Parses complex entertainment production budgets from spreadsheet data
 */

import type ExcelJS from 'exceljs';
import {
    ProductionBudget,
    BudgetDepartment,
    BudgetLineItem,
    BudgetWarning,
    COST_CODE_CATEGORIES,
    COLUMN_ALIASES,
    UnitType,
    WorkerClassification,
    DealMemoStatus,
} from './budget_schema';

/**
 * Parse a spreadsheet file into a normalized ProductionBudget
 */
export async function parseBudgetFile(file: File): Promise<ProductionBudget> {
    const buffer = await file.arrayBuffer();
    const { default: ExcelJSLib } = await import('exceljs');
    const workbook = new ExcelJSLib.Workbook();
    await workbook.xlsx.load(buffer);

    // Try to find the main budget sheet
    const sheetNames = workbook.worksheets.map(ws => ws.name);
    const sheetName = findBudgetSheet(sheetNames);
    const worksheet = workbook.getWorksheet(sheetName);
    if (!worksheet) throw new Error(`Sheet '${sheetName}' not found`);

    // Convert worksheet to 2D array (compatible with existing parser)
    const rawData: unknown[][] = [];
    worksheet.eachRow({ includeEmpty: true }, (row) => {
        const values = row.values as unknown[];
        // ExcelJS row.values is 1-indexed with undefined at [0]
        rawData.push(values.slice(1).map(v => v ?? ''));
    });

    // Detect structure and parse
    return parseRawBudgetData(rawData, file.name);
}

/**
 * Find the most likely budget sheet in a workbook
 */
function findBudgetSheet(sheetNames: string[]): string {
    const budgetKeywords = ['budget', 'topsheet', 'top sheet', 'summary', 'detail', 'main'];

    // Look for explicit budget sheet
    for (const name of sheetNames) {
        const lower = name.toLowerCase();
        if (budgetKeywords.some(kw => lower.includes(kw))) {
            return name;
        }
    }

    // Default to first sheet
    return sheetNames[0];
}

/**
 * Parse raw spreadsheet data into budget structure
 */
function parseRawBudgetData(data: unknown[][], fileName: string): ProductionBudget {
    // Step 1: Find header row
    const headerRowIndex = findHeaderRow(data);
    const headers = data[headerRowIndex] as string[];

    // Step 2: Map columns to our schema
    const columnMap = mapColumns(headers);

    // Step 3: Extract project metadata from top rows
    const metadata = extractMetadata(data.slice(0, headerRowIndex));

    // Step 4: Parse line items
    const lineItems = parseLineItems(data.slice(headerRowIndex + 1), columnMap, headers);

    // Step 5: Group into departments
    const departments = groupByDepartment(lineItems);

    // Step 6: Calculate totals
    const subtotal = departments.reduce((sum, dept) => sum + dept.subtotal, 0);
    const contingency = extractContingency(data, subtotal);
    const contingencyPercent = subtotal > 0 ? (contingency / subtotal) * 100 : 0;

    return {
        projectName: metadata.projectName || extractProjectName(fileName),
        projectCode: metadata.projectCode,
        version: metadata.version,
        date: metadata.date,
        preparedBy: metadata.preparedBy,
        departments,
        subtotal,
        contingency,
        contingencyPercent,
        fringesTotal: 0, // Will be calculated by rules engine
        grandTotal: subtotal + contingency,
    };
}

/**
 * Find the row containing column headers
 */
function findHeaderRow(data: unknown[][]): number {
    const headerKeywords = [
        'description', 'desc', 'item', 'cost', 'rate', 'qty',
        'quantity', 'total', 'extension', 'budget', 'account'
    ];

    for (let i = 0; i < Math.min(20, data.length); i++) {
        const row = data[i];
        if (!row || !Array.isArray(row)) continue;

        const rowText = row.map(cell => String(cell || '').toLowerCase()).join(' ');
        const matchCount = headerKeywords.filter(kw => rowText.includes(kw)).length;

        // Need at least 2 header keyword matches
        if (matchCount >= 2) {
            return i;
        }
    }

    // Default to row 0 if no headers found
    return 0;
}

/**
 * Map spreadsheet columns to our schema fields
 */
function mapColumns(headers: string[]): Record<string, number> {
    const mapping: Record<string, number> = {};
    const normalizedHeaders = headers.map(h => normalizeColumnName(String(h)));

    for (const [field, aliases] of Object.entries(COLUMN_ALIASES)) {
        for (let i = 0; i < normalizedHeaders.length; i++) {
            const header = normalizedHeaders[i];
            if (aliases.some(alias => header.includes(alias) || alias.includes(header))) {
                mapping[field] = i;
                break;
            }
        }
    }

    return mapping;
}

/**
 * Normalize column name for matching
 */
function normalizeColumnName(name: string): string {
    return name.toLowerCase().trim()
        .replace(/[^a-z0-9]/g, '_')
        .replace(/_+/g, '_')
        .replace(/^_|_$/g, '');
}

/**
 * Extract project metadata from header rows
 */
function extractMetadata(headerRows: unknown[][]): {
    projectName?: string;
    projectCode?: string;
    version?: string;
    date?: Date;
    preparedBy?: string;
} {
    const metadata: Record<string, string | Date | undefined> = {};

    for (const row of headerRows) {
        const rowText = row.map(c => String(c || '')).join(' ').toLowerCase();

        // Look for project name patterns
        if (rowText.includes('project') || rowText.includes('show') || rowText.includes('title')) {
            const match = row.find(c => String(c).length > 3 && !String(c).toLowerCase().includes('project'));
            if (match) metadata.projectName = String(match);
        }

        // Look for date
        if (rowText.includes('date')) {
            const dateCell = row.find(c => {
                const val = String(c);
                return /\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}/.test(val) || !isNaN(Date.parse(val));
            });
            if (dateCell) {
                metadata.date = new Date(String(dateCell));
            }
        }

        // Look for prepared by
        if (rowText.includes('prepared') || rowText.includes('by')) {
            const nameMatch = row.find(c => /^[A-Z][a-z]+ [A-Z][a-z]+$/.test(String(c)));
            if (nameMatch) metadata.preparedBy = String(nameMatch);
        }
    }

    return metadata;
}

/**
 * Extract project name from filename
 */
function extractProjectName(fileName: string): string {
    return fileName
        .replace(/\.(xlsx|xls|csv|numbers)$/i, '')
        .replace(/budget|wip|final|draft|v\d+/gi, '')
        .replace(/[_\-|]+/g, ' ')
        .trim() || 'Untitled Project';
}

/**
 * Parse line items from data rows
 */
function parseLineItems(
    rows: unknown[][],
    columnMap: Record<string, number>,
    headers: string[]
): BudgetLineItem[] {
    const items: BudgetLineItem[] = [];

    for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        if (!row || row.every(c => !c)) continue; // Skip empty rows

        // Detect if this is a section header vs line item
        const isSectionHeader = isSectionHeaderRow(row, headers);
        if (isSectionHeader) continue;

        // Extract values using column map
        const costCode = extractCostCode(row, columnMap);
        const description = String(row[columnMap.description] || row[1] || '').trim();
        const quantity = parseNumber(row[columnMap.quantity] || row[2]);
        const units = parseUnits(row[columnMap.units] || row[3]);
        const rate = parseNumber(row[columnMap.rate] || row[4]);
        const extension = parseNumber(row[columnMap.extension] || row[5]) || (quantity * rate);

        // Skip if no meaningful data
        if (!description && !extension && !rate) continue;

        // Skip subtotal/total rows
        if (isSubtotalRow(description)) continue;

        items.push({
            id: `line-${i + 1}`,
            costCode: costCode || inferCostCode(description, i),
            category: costCode ? COST_CODE_CATEGORIES[costCode.charAt(0) + '00'] || 'Other' : 'Uncategorized',
            description,
            quantity: quantity || 1,
            units: units || 'flat',
            rate,
            extension,
            vendor: String(row[columnMap.vendor] || '').trim() || undefined,
            classification: parseClassification(row[columnMap.classification]),
            dealMemoStatus: parseDealMemoStatus(row[columnMap.dealMemoStatus]),
            notes: String(row[columnMap.notes] || '').trim() || undefined,
            warnings: [],
            errors: [],
        });
    }

    return items;
}

/**
 * Extract cost code from row
 */
function extractCostCode(row: unknown[], columnMap: Record<string, number>): string | undefined {
    const codeValue = row[columnMap.costCode] || row[0];
    if (!codeValue) return undefined;

    const code = String(codeValue).trim();

    // Match patterns: "100", "201", "301.1", etc.
    const match = code.match(/^(\d{3})(\.\d+)?$/);
    if (match) return code;

    // Also check for embedded codes
    const embedded = code.match(/(\d{3})(\.\d+)?/);
    if (embedded) return embedded[0];

    return undefined;
}

/**
 * Infer cost code from description
 */
function inferCostCode(description: string, index: number): string {
    const lower = description.toLowerCase();

    // Keywords to cost code mapping
    const keywords: Record<string, string> = {
        'producer': '101',
        'director': '102',
        'writer': '103',
        'talent': '104',
        'cast': '104',
        'camera': '301',
        'dp': '301',
        'cinematograph': '301',
        'gaffer': '302',
        'lighting': '302',
        'electric': '302',
        'grip': '303',
        'art': '401',
        'production design': '401',
        'set': '402',
        'props': '403',
        'wardrobe': '404',
        'makeup': '405',
        'hair': '405',
        'sound': '501',
        'audio': '501',
        'edit': '502',
        'post': '502',
        'vfx': '503',
        'music': '504',
        'insurance': '701',
        'legal': '702',
        'location': '601',
        'transport': '602',
        'catering': '603',
        'craft': '604',
    };

    for (const [keyword, code] of Object.entries(keywords)) {
        if (lower.includes(keyword)) return code;
    }

    return `900.${index + 1}`; // Misc fallback
}

/**
 * Detect section header rows
 */
function isSectionHeaderRow(row: unknown[], headers: string[]): boolean {
    // Section headers typically have fewer filled cells
    const filledCells = row.filter(c => c !== null && c !== undefined && c !== '').length;
    if (filledCells <= 2) {
        const text = row.map(c => String(c).toLowerCase()).join(' ');
        const sectionKeywords = ['total', 'subtotal', 'production', 'above the line', 'below the line',
            'camera', 'lighting', 'art', 'post', 'general', 'department'];
        return sectionKeywords.some(kw => text.includes(kw));
    }
    return false;
}

/**
 * Detect subtotal/total rows
 */
function isSubtotalRow(description: string): boolean {
    const lower = description.toLowerCase();
    return ['total', 'subtotal', 'sub total', 'grand total', 'sum', 'budget total']
        .some(kw => lower.includes(kw));
}

/**
 * Parse number from various formats
 */
function parseNumber(value: unknown): number {
    if (typeof value === 'number') return value;
    if (!value) return 0;

    const str = String(value).replace(/[$,\s]/g, '');
    const num = parseFloat(str);
    return isNaN(num) ? 0 : num;
}

/**
 * Parse unit type
 */
function parseUnits(value: unknown): UnitType {
    const str = String(value || '').toLowerCase().trim();

    const unitMap: Record<string, UnitType> = {
        'day': 'day',
        'days': 'day',
        'd': 'day',
        'week': 'week',
        'weeks': 'week',
        'wk': 'week',
        'flat': 'flat',
        'f': 'flat',
        'hour': 'hour',
        'hours': 'hour',
        'hr': 'hour',
        'hrs': 'hour',
        'allow': 'allow',
        'allowance': 'allow',
        'kit': 'kit',
        'each': 'each',
        'ea': 'each',
        'run': 'run',
    };

    return unitMap[str] || 'flat';
}

/**
 * Parse worker classification
 */
function parseClassification(value: unknown): WorkerClassification | undefined {
    const str = String(value || '').toLowerCase().trim();

    if (str.includes('1099') || str.includes('contractor')) return '1099';
    if (str.includes('w-2') || str.includes('w2') || str.includes('employee')) return 'W-2';
    if (str.includes('loan') || str.includes('loanout') || str.includes('loan-out')) return 'loan-out';
    if (str.includes('corp') || str.includes('c2c')) return 'corp-to-corp';

    return undefined;
}

/**
 * Parse deal memo status
 */
function parseDealMemoStatus(value: unknown): DealMemoStatus | undefined {
    const str = String(value || '').toLowerCase().trim();

    if (str.includes('need') || str.includes('pending')) return 'need_to_send';
    if (str.includes('sent') && !str.includes('signed')) return 'sent';
    if (str.includes('signed')) return 'signed';
    if (str.includes('complete') || str.includes('done')) return 'complete';
    if (str.includes('n/a') || str.includes('not required')) return 'not_required';

    return undefined;
}

/**
 * Group line items by department
 */
function groupByDepartment(items: BudgetLineItem[]): BudgetDepartment[] {
    const deptMap = new Map<string, BudgetLineItem[]>();

    for (const item of items) {
        const deptCode = item.costCode.charAt(0) + '00';
        if (!deptMap.has(deptCode)) {
            deptMap.set(deptCode, []);
        }
        deptMap.get(deptCode)!.push(item);
    }

    return Array.from(deptMap.entries()).map(([code, lineItems]) => ({
        code,
        name: COST_CODE_CATEGORIES[code] || `Category ${code}`,
        lineItems,
        subtotal: lineItems.reduce((sum, item) => sum + item.extension, 0),
    })).sort((a, b) => a.code.localeCompare(b.code));
}

/**
 * Extract contingency from budget data
 */
function extractContingency(data: unknown[][], subtotal: number): number {
    // Look for contingency row
    for (const row of data) {
        const rowText = row?.map(c => String(c || '').toLowerCase()).join(' ') || '';
        if (rowText.includes('contingency')) {
            // Find the numeric value
            for (const cell of row) {
                const num = parseNumber(cell);
                if (num > 0) {
                    // If it's a percentage, calculate
                    if (num < 100) return subtotal * (num / 100);
                    return num;
                }
            }
        }
    }

    // Default to 10% if not found
    return subtotal * 0.10;
}

export { parseRawBudgetData };
