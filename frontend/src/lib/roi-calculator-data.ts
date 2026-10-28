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
        ],
        leadGate: {
            title: 'Your Illustrative Savings Estimate is Ready',
            description: 'Enter your work email to see the illustrative breakdown. The numbers are not a forecast or commitment. Book a call to model against your actual record volume.',
            cta: 'View My Estimate'
        }
    }
};

export const calculateROI = (answers: Record<string, any>) => {
    const weeklyRecords = Number(answers['weekly-records'] || 0);
    const manualHours = Number(answers['manual-hours'] || 0);

    // ILLUSTRATIVE COEFFICIENTS - not forecasts, not industry benchmarks. Surfaced
    // honestly in the user-facing Methodology Note. Results are hours per year,
    // never dollars: the public site carries no dollar amounts (A-2169).
    //
    // 1. Modeled labor time avoided: ManualHours * 52 weeks * 0.85 capture rate
    const laborHours = manualHours * 52 * 0.85;

    // 2. Modeled operational time: WeeklyRecords * 0.5 min saved * 52 weeks * 0.95
    const rawOperationalHours = (weeklyRecords * 0.5 / 60) * 52 * 0.95;

    // Cap operational time at 35% of labor time to avoid overly optimistic results
    const operationalHours = Math.min(rawOperationalHours, laborHours * 0.35);

    const totalHours = laborHours + operationalHours;

    return {
        laborHours,
        operationalHours,
        totalHours,
    };
};
