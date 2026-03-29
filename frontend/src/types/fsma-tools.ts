export type ToolStatus = 'START' | 'QUESTIONS' | 'RESULTS';

/** A single answer value from a tool question (scalar or multi-select array). */
export type AnswerValue = string | number | boolean | (string | number | boolean)[];

/** Map of question ID to answer value. */
export type ToolAnswers = Record<string, AnswerValue>;

export interface ToolQuestion {
    id: string;
    text: string;
    type: 'select' | 'boolean' | 'number' | 'multi-select' | 'text';
    options?: { label: string; value: string | number | boolean; weight?: number }[];
    placeholder?: string;
    hint?: string;
    dependency?: { questionId: string; value: string | number | boolean };
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
    scoring?: (answers: ToolAnswers) => unknown;
}

export interface LeadData {
    email: string;
    entityName?: string;
    entityType?: string;
    intentScore: number;
    toolId: string;
    resultsSummary: string;
    answers?: ToolAnswers;
}
