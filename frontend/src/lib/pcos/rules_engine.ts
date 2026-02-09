/**
 * Production Budget Rules Engine
 * Analyzes budgets for compliance, optimization, and tax opportunities
 */

import {
    ProductionBudget,
    BudgetAnalysis,
    BudgetWarning,
    BudgetLineItem,
    TaxCreditCheck,
    CloseoutItem,
    UNION_RATE_MINIMUMS,
    POSITION_KEYWORDS,
} from './budget_schema';

/**
 * Run full analysis on a parsed budget
 */
export function analyzeBudget(budget: ProductionBudget): BudgetAnalysis {
    const warnings: BudgetWarning[] = [];

    // Run all rule categories
    const complianceIssues = runComplianceRules(budget);
    const optimizationOpportunities = runOptimizationRules(budget);
    const taxCreditEligibility = runTaxCreditRules(budget);
    const closeoutChecklist = generateCloseoutChecklist(budget);

    // Calculate risk score
    const criticalCount = complianceIssues.filter(w => w.severity === 'critical').length;
    const warningCount = complianceIssues.filter(w => w.severity === 'warning').length;
    const riskScore = Math.min(100, criticalCount * 20 + warningCount * 5);

    // Calculate potential savings/exposure
    const potentialSavings = optimizationOpportunities
        .reduce((sum, w) => sum + (extractDollarAmount(w.message) || 0), 0);
    const potentialExposure = complianceIssues
        .filter(w => w.severity === 'critical')
        .reduce((sum, w) => sum + (extractDollarAmount(w.message) || budget.grandTotal * 0.05), 0);

    return {
        timestamp: new Date(),
        totalWarnings: complianceIssues.length + optimizationOpportunities.length,
        totalErrors: 0,
        riskScore,
        complianceIssues,
        optimizationOpportunities,
        taxCreditEligibility,
        closeoutChecklist,
        potentialSavings,
        potentialExposure,
    };
}

/**
 * COMPLIANCE RULES
 * Check for labor law, union, and paperwork compliance
 */
function runComplianceRules(budget: ProductionBudget): BudgetWarning[] {
    const warnings: BudgetWarning[] = [];

    // Rule 1: Union Rate Minimums
    warnings.push(...checkUnionRates(budget));

    // Rule 2: Worker Classification
    warnings.push(...checkWorkerClassification(budget));

    // Rule 3: Deal Memo Completeness
    warnings.push(...checkDealMemos(budget));

    // Rule 4: Contingency Sanity Check
    warnings.push(...checkContingency(budget));

    // Rule 5: Missing Required Fields
    warnings.push(...checkRequiredFields(budget));

    return warnings;
}

/**
 * Check for union rate compliance
 */
function checkUnionRates(budget: ProductionBudget): BudgetWarning[] {
    const warnings: BudgetWarning[] = [];

    for (const dept of budget.departments) {
        for (const item of dept.lineItems) {
            const position = detectPosition(item.description);
            if (!position) continue;

            const minRate = UNION_RATE_MINIMUMS[position];
            if (minRate && item.rate > 0 && item.rate < minRate) {
                warnings.push({
                    code: 'UNION_RATE_BELOW_MINIMUM',
                    severity: 'warning',
                    category: 'compliance',
                    lineItemId: item.id,
                    message: `${item.description}: Rate $${item.rate}/day is below union minimum of $${minRate}/day for ${position.replace(/_/g, ' ')}`,
                    recommendation: `Consider adjusting to at least $${minRate}/day to avoid grievances or back-pay claims`,
                    resourceUrl: 'https://www.iatse.net/wage-scales',
                });
            }
        }
    }

    return warnings;
}

/**
 * Check worker classification rules
 */
function checkWorkerClassification(budget: ProductionBudget): BudgetWarning[] {
    const warnings: BudgetWarning[] = [];

    // Positions that should almost always be W-2 in California
    const w2Positions = ['pa', 'production_assistant', 'electrician', 'grip', 'first_ac', 'second_ac'];

    for (const dept of budget.departments) {
        for (const item of dept.lineItems) {
            const position = detectPosition(item.description);

            // Check for misclassification risk
            if (position && w2Positions.includes(position) && item.classification === '1099') {
                warnings.push({
                    code: 'MISCLASSIFICATION_RISK',
                    severity: 'critical',
                    category: 'compliance',
                    lineItemId: item.id,
                    message: `${item.description}: Classified as 1099 but position typically requires W-2 status under CA AB5`,
                    recommendation: `Review worker classification. Under AB5, ${position.replace(/_/g, ' ')} roles typically fail the ABC test and should be payrolled`,
                    resourceUrl: 'https://www.dir.ca.gov/dlse/faq_independentcontractor.htm',
                });
            }

            // Check for high-volume 1099 usage
            if (item.classification === '1099' && item.quantity > 10) {
                warnings.push({
                    code: 'HIGH_VOLUME_1099',
                    severity: 'warning',
                    category: 'compliance',
                    lineItemId: item.id,
                    message: `${item.description}: ${item.quantity} days as 1099 may trigger audit attention`,
                    recommendation: 'Consider payroll for extended engagements to reduce classification risk',
                });
            }
        }
    }

    return warnings;
}

/**
 * Check deal memo completeness
 */
function checkDealMemos(budget: ProductionBudget): BudgetWarning[] {
    const warnings: BudgetWarning[] = [];

    let needToSend = 0;
    let sent = 0;
    let total = 0;

    for (const dept of budget.departments) {
        for (const item of dept.lineItems) {
            if (!item.dealMemoStatus || item.dealMemoStatus === 'not_required') continue;

            total++;
            if (item.dealMemoStatus === 'need_to_send') needToSend++;
            if (item.dealMemoStatus === 'sent') sent++;

            if (item.dealMemoStatus === 'need_to_send') {
                warnings.push({
                    code: 'DEAL_MEMO_MISSING',
                    severity: 'warning',
                    category: 'paperwork',
                    lineItemId: item.id,
                    message: `${item.description}: Deal memo needs to be sent`,
                    recommendation: 'Send deal memo immediately to avoid disputes',
                });
            }
        }
    }

    // Overall paperwork summary
    if (needToSend > 0 || sent > 0) {
        warnings.push({
            code: 'PAPERWORK_INCOMPLETE',
            severity: needToSend > 5 ? 'critical' : 'warning',
            category: 'paperwork',
            message: `Paperwork status: ${needToSend} deal memos need sending, ${sent} awaiting signature (${total} total)`,
            recommendation: 'Generate deal memo chase list and set signature deadlines',
        });
    }

    return warnings;
}

/**
 * Check contingency calculation
 */
function checkContingency(budget: ProductionBudget): BudgetWarning[] {
    const warnings: BudgetWarning[] = [];

    // Check if contingency is reasonable
    if (budget.contingencyPercent < 5) {
        warnings.push({
            code: 'CONTINGENCY_LOW',
            severity: 'warning',
            category: 'compliance',
            message: `Contingency at ${budget.contingencyPercent.toFixed(1)}% is below industry standard (typically 10%)`,
            recommendation: 'Consider increasing contingency to 10% for unexpected costs',
        });
    } else if (budget.contingencyPercent > 15) {
        warnings.push({
            code: 'CONTINGENCY_HIGH',
            severity: 'info',
            category: 'compliance',
            message: `Contingency at ${budget.contingencyPercent.toFixed(1)}% is above typical range`,
            recommendation: 'Verify contingency calculation base - may indicate budget padding',
        });
    }

    // Check if contingency base is unclear
    const expectedContingency = budget.subtotal * 0.10;
    const variance = Math.abs(budget.contingency - expectedContingency) / expectedContingency;

    if (variance > 0.1 && budget.contingencyPercent >= 9 && budget.contingencyPercent <= 11) {
        warnings.push({
            code: 'CONTINGENCY_BASE_UNCLEAR',
            severity: 'info',
            category: 'compliance',
            message: `Contingency labeled as 10% but doesn't match full subtotal - may exclude protected lines`,
            recommendation: 'Document which line items are contingency-eligible vs protected',
        });
    }

    return warnings;
}

/**
 * Check for missing required fields
 */
function checkRequiredFields(budget: ProductionBudget): BudgetWarning[] {
    const warnings: BudgetWarning[] = [];

    let missingRates = 0;
    let missingDescriptions = 0;

    for (const dept of budget.departments) {
        for (const item of dept.lineItems) {
            if (!item.description) missingDescriptions++;
            if (item.extension > 0 && item.rate === 0 && item.quantity === 0) missingRates++;
        }
    }

    if (missingDescriptions > 0) {
        warnings.push({
            code: 'MISSING_DESCRIPTIONS',
            severity: 'warning',
            category: 'compliance',
            message: `${missingDescriptions} line items missing descriptions - makes auditing difficult`,
            recommendation: 'Add descriptions to all line items for clear cost reporting',
        });
    }

    if (missingRates > 0) {
        warnings.push({
            code: 'FLAT_AMOUNTS_NO_RATES',
            severity: 'info',
            category: 'compliance',
            message: `${missingRates} line items have totals but no rate/qty breakdown`,
            recommendation: 'Consider breaking flat amounts into rate × quantity for transparency',
        });
    }

    return warnings;
}

/**
 * OPTIMIZATION RULES
 * Find cost savings and efficiency opportunities
 */
function runOptimizationRules(budget: ProductionBudget): BudgetWarning[] {
    const warnings: BudgetWarning[] = [];

    // Rule 1: Camera package economics
    warnings.push(...checkCameraPackage(budget));

    // Rule 2: Crafty vs Catering split
    warnings.push(...checkCraftyCatering(budget));

    // Rule 3: Deposit recovery
    warnings.push(...checkDepositRecovery(budget));

    // Rule 4: Duplicate detection
    warnings.push(...checkDuplicates(budget));

    // Rule 5: Misc bucket drill-down
    warnings.push(...checkMiscBucket(budget));

    return warnings;
}

/**
 * Check camera package economics
 */
function checkCameraPackage(budget: ProductionBudget): BudgetWarning[] {
    const warnings: BudgetWarning[] = [];

    for (const dept of budget.departments) {
        if (dept.code !== '300') continue;

        for (const item of dept.lineItems) {
            const lower = item.description.toLowerCase();

            // Check for expensive rental packages
            if ((lower.includes('camera') || lower.includes('package')) && item.extension > 5000) {
                const shootDays = budget.departments
                    .flatMap(d => d.lineItems)
                    .filter(i => i.units === 'day')
                    .reduce((max, i) => Math.max(max, i.quantity), 5);

                const costPerDay = item.extension / shootDays;

                if (costPerDay > 1500) {
                    warnings.push({
                        code: 'CAMERA_PACKAGE_EXPENSIVE',
                        severity: 'info',
                        category: 'optimization',
                        lineItemId: item.id,
                        message: `Camera package at ~$${costPerDay.toFixed(0)}/day may have negotiation room`,
                        recommendation: 'Request weekly rates, negotiate pickup/return days, or split kit fee from rental',
                        resourceUrl: 'https://www.sharegrid.com/losangeles',
                    });
                }
            }
        }
    }

    return warnings;
}

/**
 * Check crafty/catering separation
 */
function checkCraftyCatering(budget: ProductionBudget): BudgetWarning[] {
    const warnings: BudgetWarning[] = [];

    for (const dept of budget.departments) {
        for (const item of dept.lineItems) {
            const lower = item.description.toLowerCase();

            // Check for bundled meals
            if ((lower.includes('crafty') && lower.includes('catering')) ||
                (lower.includes('meals') && lower.includes('snacks'))) {
                warnings.push({
                    code: 'BUNDLED_MEALS',
                    severity: 'info',
                    category: 'optimization',
                    lineItemId: item.id,
                    message: `Crafty and catering appear bundled - consider separating for better cost control`,
                    recommendation: 'Split into: Catering (hot meals) vs Craft Service (snacks/coffee) for easier auditing and meal penalty compliance',
                });
            }
        }
    }

    return warnings;
}

/**
 * Check for deposit recovery opportunities
 */
function checkDepositRecovery(budget: ProductionBudget): BudgetWarning[] {
    const warnings: BudgetWarning[] = [];

    const depositKeywords = ['rental', 'camera', 'lighting', 'grip', 'vehicle', 'location', 'walkie', 'radio'];
    const depositItems: string[] = [];

    for (const dept of budget.departments) {
        for (const item of dept.lineItems) {
            const lower = item.description.toLowerCase();
            if (depositKeywords.some(kw => lower.includes(kw))) {
                depositItems.push(item.description);
            }
        }
    }

    if (depositItems.length > 0) {
        warnings.push({
            code: 'DEPOSIT_RECOVERY_CHECK',
            severity: 'info',
            category: 'optimization',
            message: `${depositItems.length} line items likely have deposits to recover: rentals, locations, vehicles`,
            recommendation: 'Generate "Deposits Outstanding" checklist before wrap to recover all security deposits',
        });
    }

    return warnings;
}

/**
 * Check for potential duplicate entries
 */
function checkDuplicates(budget: ProductionBudget): BudgetWarning[] {
    const warnings: BudgetWarning[] = [];

    const items: { desc: string; amount: number; id: string }[] = [];

    for (const dept of budget.departments) {
        for (const item of dept.lineItems) {
            items.push({
                desc: item.description.toLowerCase().replace(/\s+/g, ' ').trim(),
                amount: item.extension,
                id: item.id,
            });
        }
    }

    // Find similar descriptions with same amounts
    const seen = new Map<string, string[]>();

    for (const item of items) {
        const key = `${item.desc.substring(0, 20)}-${item.amount}`;
        if (!seen.has(key)) {
            seen.set(key, []);
        }
        seen.get(key)!.push(item.id);
    }

    for (const [key, ids] of Array.from(seen.entries())) {
        if (ids.length > 1) {
            warnings.push({
                code: 'POSSIBLE_DUPLICATE',
                severity: 'warning',
                category: 'optimization',
                message: `Possible duplicate entries detected: ${ids.length} similar items with same amount`,
                recommendation: 'Review for duplicate payments - fuzzy match detected on description + amount',
            });
            break; // Only report once
        }
    }

    return warnings;
}

/**
 * Check misc bucket size
 */
function checkMiscBucket(budget: ProductionBudget): BudgetWarning[] {
    const warnings: BudgetWarning[] = [];

    const miscDept = budget.departments.find(d => d.code === '900');
    if (!miscDept) return warnings;

    const miscPercent = (miscDept.subtotal / budget.grandTotal) * 100;

    if (miscPercent > 5) {
        warnings.push({
            code: 'MISC_BUCKET_LARGE',
            severity: 'warning',
            category: 'optimization',
            message: `Miscellaneous at $${miscDept.subtotal.toLocaleString()} (${miscPercent.toFixed(1)}% of budget) - where unsupported spend hides`,
            recommendation: 'Force reclass: Accounting, Office, Deliverables, Legal, or Other for audit clarity',
        });
    }

    return warnings;
}

/**
 * TAX CREDIT RULES
 * Pre-screen for incentive eligibility
 */
function runTaxCreditRules(budget: ProductionBudget): TaxCreditCheck[] {
    const checks: TaxCreditCheck[] = [];

    // California Film Tax Credit
    checks.push({
        jurisdiction: 'CA',
        programName: 'California Film & Television Tax Credit Program 4.0',
        eligible: budget.grandTotal >= 1000000 ? 'maybe' : false,
        reason: budget.grandTotal >= 1000000
            ? 'Budget meets minimum spend threshold. Requires 75% CA filming and lottery application.'
            : `Budget of $${budget.grandTotal.toLocaleString()} below $1M minimum for features`,
        qualifiedSpend: budget.grandTotal * 0.7, // Estimate
        estimatedCredit: budget.grandTotal >= 1000000 ? budget.grandTotal * 0.7 * 0.25 : 0,
        requirements: [
            'Minimum $1M budget for features',
            '75% principal photography in CA',
            'Apply through lottery system',
            'Relocating TV series get priority',
        ],
        contactUrl: 'https://film.ca.gov/tax-credit/',
        filmCommissionPhone: '(323) 860-2960',
    });

    // Georgia
    checks.push({
        jurisdiction: 'GA',
        programName: 'Georgia Entertainment Production Tax Credit',
        eligible: budget.grandTotal >= 500000 ? 'maybe' : false,
        reason: budget.grandTotal >= 500000
            ? 'Budget meets $500K minimum. 20% base + 10% logo bonus possible.'
            : `Budget below $500K Georgia minimum`,
        qualifiedSpend: budget.grandTotal * 0.8,
        estimatedCredit: budget.grandTotal >= 500000 ? budget.grandTotal * 0.8 * 0.30 : 0,
        requirements: [
            'Minimum $500K Georgia spend',
            'Include Georgia logo in credits for +10%',
            'Transferable credits',
        ],
        contactUrl: 'https://www.georgia.org/georgia-film-tv-production',
        filmCommissionPhone: '(404) 962-4052',
    });

    // New Mexico
    checks.push({
        jurisdiction: 'NM',
        programName: 'New Mexico Film Production Tax Credit',
        eligible: 'maybe',
        reason: 'NM offers 25-35% refundable credit with no minimum spend',
        qualifiedSpend: budget.grandTotal * 0.75,
        estimatedCredit: budget.grandTotal * 0.75 * 0.25,
        requirements: [
            'No minimum spend requirement',
            '25% base credit, +5% for qualifying counties',
            '+5% for TV series (additional episodes)',
            'Refundable credit (cash back)',
        ],
        contactUrl: 'https://nmfilm.com/film-incentives/',
        filmCommissionPhone: '(505) 476-5600',
    });

    return checks;
}

/**
 * Generate closeout checklist
 */
function generateCloseoutChecklist(budget: ProductionBudget): CloseoutItem[] {
    const items: CloseoutItem[] = [];

    // Paperwork items
    items.push({
        category: 'paperwork',
        item: 'All deal memos executed',
        status: 'pending',
    });
    items.push({
        category: 'paperwork',
        item: 'Startwork/I-9/W-4 complete for all payrolled crew',
        status: 'pending',
    });
    items.push({
        category: 'paperwork',
        item: 'W-9s collected from all 1099 vendors',
        status: 'pending',
    });
    items.push({
        category: 'paperwork',
        item: 'Certificates of Insurance on file for all vendors',
        status: 'pending',
    });

    // Vendor items
    items.push({
        category: 'vendor',
        item: 'All rental deposits recovered',
        status: 'pending',
    });
    items.push({
        category: 'vendor',
        item: 'Final vendor invoices received and reconciled',
        status: 'pending',
    });
    items.push({
        category: 'vendor',
        item: 'Check for duplicate payments before final AP',
        status: 'pending',
    });

    // Compliance items
    items.push({
        category: 'compliance',
        item: 'Worker classification review complete',
        status: 'pending',
    });
    items.push({
        category: 'compliance',
        item: 'Union fringe reports submitted (if applicable)',
        status: 'pending',
    });
    items.push({
        category: 'compliance',
        item: 'Tax incentive documentation collected',
        status: 'pending',
    });

    // Deliverables
    items.push({
        category: 'deliverable',
        item: 'Final cost report prepared',
        status: 'pending',
    });
    items.push({
        category: 'deliverable',
        item: 'Wrap book assembled',
        status: 'pending',
    });

    return items;
}

/**
 * Detect position from description
 */
function detectPosition(description: string): string | undefined {
    const lower = description.toLowerCase();

    for (const [position, keywords] of Object.entries(POSITION_KEYWORDS)) {
        if (keywords.some(kw => lower.includes(kw))) {
            return position;
        }
    }

    return undefined;
}

/**
 * Extract dollar amount from message
 */
function extractDollarAmount(message: string): number | undefined {
    const match = message.match(/\$[\d,]+/);
    if (match) {
        return parseFloat(match[0].replace(/[$,]/g, ''));
    }
    return undefined;
}


