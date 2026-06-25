import { ToolConfig } from '@/types/fsma-tools';

export const ROI_CALCULATOR_CONFIG: ToolConfig = {
    id: 'roi-calculator',
    title: 'FSMA 204 Savings Estimator',
    description: 'Get an illustrative sense of where traceability workflow automation could pay back. Numbers depend on your inputs and on assumptions we publish in the methodology note. Not a forecast.',
    icon: 'TrendingUp',
    stages: {
        questions: [
            {
                id: 'entity-type',
                text: 'What is your primary trading role?',
                type: 'select',
                options: [
                    { label: 'Manufacturer / Processor', value: 'manufacturer' },
                    { label: 'Distributor / Wholesaler', value: 'distributor' },
                    { label: 'Retailer / Food Service', value: 'retailer' },
                    { label: 'Importer', value: 'importer' }
                ]
            },
            {
                id: 'weekly-records',
                text: 'Approximately how many traceability records (KDEs) do you manage per week?',
                type: 'select',
                options: [
                    { label: 'Less than 1,000', value: 500 },
                    { label: '1,000 - 5,000', value: 3000 },
                    { label: '5,000 - 20,000', value: 12500 },
                    { label: 'Over 20,000', value: 50000 }
                ]
            },
            {
                id: 'manual-hours',
                text: 'How many hours per week does your team spend on manual data entry or document retrieval?',
                type: 'select',
                options: [
                    { label: '0 - 10 hours', value: 5 },
                    { label: '10 - 40 hours', value: 25 },
                    { label: '40 - 100 hours', value: 70 },
                    { label: 'Over 100 hours', value: 150 }
                ]
            },
            {
                id: 'annual-revenue',
                text: 'What is your approximate annual revenue?',
                type: 'select',
                options: [
                    { label: 'Under $10M', value: 5000000 },
                    { label: '$10M - $100M', value: 50000000 },
                    { label: '$100M - $1B', value: 500000000 },
                    { label: 'Over $1B', value: 2000000000 }
                ]
            }
        ],
        leadGate: {
            title: 'Your Illustrative Savings Estimate is Ready',
            description: 'Enter your work email to see the illustrative breakdown. The numbers are not a forecast or commitment — book a call to model against your actual record volume.',
            cta: 'View My Estimate'
        }
    }
};

export const calculateROI = (answers: Record<string, any>) => {
    const weeklyRecords = Number(answers['weekly-records'] || 0);
    const manualHours = Number(answers['manual-hours'] || 0);
    const annualRevenue = Number(answers['annual-revenue'] || 0);

    // ILLUSTRATIVE COEFFICIENTS — not forecasts, not industry benchmarks. Surfaced
    // honestly in the user-facing Methodology Note. Adjust here if assumptions change.
    //
    // 1. Modeled labor-time avoided: ManualHours * $75/hr loaded rate * 52 weeks * 0.85 capture rate
    const laborSavings = manualHours * 75 * 52 * 0.85;

    // 2. Modeled risk concentration placeholder: Revenue * 0.05% * 0.90. There is no
    //    public FSMA 204 fine schedule; this is a small fraction of revenue used as a
    //    rough placeholder, NOT an expected violation cost.
    const riskReduction = annualRevenue * 0.0005 * 0.90;

    // 3. Modeled operational time: WeeklyRecords * 0.5 min saved * $75/hr * 52 weeks * 0.95
    const rawOperationalEfficiency = (weeklyRecords * 0.5 / 60) * 75 * 52 * 0.95;

    // Cap operational efficiency at 35% of the total benefit to avoid overly optimistic results
    const baseBenefit = laborSavings + riskReduction;
    const operationalEfficiency = Math.min(rawOperationalEfficiency, baseBenefit * 0.35);

    const totalBenefit = baseBenefit + operationalEfficiency;

    // Estimated platform cost
    let platformCost = 25000;
    if (annualRevenue > 1000000000) platformCost = 150000;
    else if (annualRevenue > 100000000) platformCost = 75000;

    const netBenefit = totalBenefit - platformCost;
    const paybackMonths = (platformCost / totalBenefit) * 12;
    const roi = (netBenefit / platformCost) * 100;

    return {
        laborSavings,
        riskReduction,
        operationalEfficiency,
        totalBenefit,
        platformCost,
        netBenefit,
        paybackMonths,
        roi
    };
};
