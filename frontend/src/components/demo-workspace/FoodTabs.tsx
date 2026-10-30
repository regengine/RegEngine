'use client';

import { useRef, type KeyboardEvent } from 'react';
import { shortLabel, type Scenario } from '@/lib/demo-workspace/model';
import { cn } from '@/lib/utils';
import { HueDot } from './HueDot';

interface FoodTabsProps {
  all: readonly Scenario[];
  selected: number;
  onPick: (index: number) => void;
  size?: 'sm' | 'md';
  className?: string;
}

/** One pill per FTL food. Roving tabindex, arrow keys move the selection. */
export function FoodTabs({ all, selected, onPick, size = 'md', className }: FoodTabsProps) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number | null = null;
    if (event.key === 'ArrowRight') next = (index + 1) % all.length;
    if (event.key === 'ArrowLeft') next = (index - 1 + all.length) % all.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = all.length - 1;
    if (next === null) return;
    event.preventDefault();
    onPick(next);
    refs.current[next]?.focus();
  };

  return (
    <div role="tablist" aria-label="FTL food" className={cn('flex flex-wrap gap-1.5', className)}>
      {all.map((scenario, index) => {
        const active = index === selected;
        return (
          <button
            key={scenario.id}
            ref={(el) => {
              refs.current[index] = el;
            }}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onPick(index)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={cn(
              'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border font-semibold transition-colors duration-120 hover:border-re-brand hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none',
              size === 'sm' ? 'px-2.5 py-1 text-small' : 'px-3 py-1.5 text-[0.8125rem]',
              active
                ? 'border-re-brand bg-re-brand-muted text-re-text-primary'
                : 'border-re-border-subtle bg-transparent text-re-text-tertiary',
            )}
          >
            <HueDot hue={scenario.hue} size="sm" />
            {shortLabel(scenario)}
          </button>
        );
      })}
    </div>
  );
}
