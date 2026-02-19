export type ToolStatus = 'START' | 'QUESTIONS' | 'RESULTS';

export interface ToolQuestion {
    id: string;
    text: string;
    type: 'select' | 'boolean' | 'number' | 'multi-select' | 'text';
    options?: { label: string; value: any; weight?: number }[];
    placeholder?: string;
    hint?: string;
    dependency?: { questionId: string; value: any };
}

export interface ToolConfig {
    id: string;
    title: string;
    description: string;
    icon: string;
    stages: {
        questions: ToolQuestion[];
        leadGate?: {
            title: string;
            description: string;
            cta: string;
        };
    };
    scoring?: (answers: Record<string, any>) => any;
}

export interface LeadData {
    email: string;
    entityName?: string;
    entityType?: string;
    intentScore: number;
    toolId: string;
    resultsSummary: string;
}
