'use client';

import { Button } from '@/components/ui/button';
import type { ActionableCteSuggestion } from '@/lib/cte-suggestion';

interface CteSuggestionPromptProps {
  suggestion: ActionableCteSuggestion;
  onImport: (cteType: string) => void;
  disabled?: boolean;
}

/**
 * Offers the CTE Jev suggested for a CSV the server rejected for having none.
 * Nothing is imported until the uploader clicks: the click re-uploads the
 * same file with `cte_type` set, which the server treats as declared.
 */
export function CteSuggestionPrompt({ suggestion, onImport, disabled = false }: CteSuggestionPromptProps) {
  const confidence = suggestion.confidence === null
    ? ''
    : ` (${Math.round(suggestion.confidence * 100)}% confidence)`;
  return (
    <div className="mt-3 space-y-2">
      <p>
        These rows look like {suggestion.label} events{confidence}.
      </p>
      <Button
        type="button"
        size="sm"
        variant="secondary"
        disabled={disabled}
        onClick={() => onImport(suggestion.cteType)}
      >
        Import as {suggestion.label}
      </Button>
      <p className="text-small text-re-text-tertiary">
        Suggested by TypeSafe Jev from the column headers. Nothing is imported until you confirm.
      </p>
    </div>
  );
}
