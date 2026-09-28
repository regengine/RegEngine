'use client';

import type { ColumnSuggestion } from '@/lib/column-suggestions';

interface ColumnSuggestionListProps {
  suggestions: ColumnSuggestion[];
}

/**
 * Jev's reading of CSV columns the parser did not recognise. Advisory only:
 * the uploader renames the column in the file and uploads it again, so
 * nothing changes until they do.
 */
export function ColumnSuggestionList({ suggestions }: ColumnSuggestionListProps) {
  if (suggestions.length === 0) return null;
  return (
    <div className="mt-3 space-y-1">
      <p>Column suggestions:</p>
      <ul className="list-inside list-disc">
        {suggestions.map((suggestion) => (
          <li key={suggestion.header}>
            &ldquo;{suggestion.header}&rdquo; looks like {suggestion.label}
            {suggestion.confidence === null ? '' : ` (${Math.round(suggestion.confidence * 100)}% confidence)`}.
            Rename the column to &ldquo;{suggestion.label}&rdquo; and upload again.
          </li>
        ))}
      </ul>
      <p className="text-small text-re-text-tertiary">
        Suggested by TypeSafe Jev from the column headers. Your file is not changed.
      </p>
    </div>
  );
}
