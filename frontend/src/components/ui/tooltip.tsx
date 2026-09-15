'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: 'top' | 'bottom' | 'left' | 'right';
  className?: string;
}

export function Tooltip({ content, children, side = 'top', className }: TooltipProps) {
  const [isVisible, setIsVisible] = React.useState(false);

  const sideClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  };

  const arrowClasses = {
    top: 'top-full left-1/2 -translate-x-1/2 border-t-re-surface-inverse border-x-transparent border-b-transparent',
    bottom: 'bottom-full left-1/2 -translate-x-1/2 border-b-re-surface-inverse border-x-transparent border-t-transparent',
    left: 'left-full top-1/2 -translate-y-1/2 border-l-re-surface-inverse border-y-transparent border-r-transparent',
    right: 'right-full top-1/2 -translate-y-1/2 border-r-re-surface-inverse border-y-transparent border-l-transparent',
  };

  return (
    // A <span>, not a <div>: this renders inside PageHeader's description,
    // CardDescription and Field hints, which are <p> elements. A block-level
    // root there is invalid HTML and React reports a hydration error.
    <span
      className="relative inline-flex"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
      onFocus={() => setIsVisible(true)}
      onBlur={() => setIsVisible(false)}
    >
      {children}
      {isVisible && (
        <span
          className={cn(
            'absolute z-[var(--re-z-popover)] block max-w-xs whitespace-normal rounded-md bg-re-surface-inverse px-3 py-2 text-small text-re-text-inverse',
            sideClasses[side],
            className
          )}
          role="tooltip"
        >
          {content}
          <span
            className={cn(
              'absolute h-0 w-0 border-4',
              arrowClasses[side]
            )}
          />
        </span>
      )}
    </span>
  );
}

interface HelpTooltipProps {
  content: string;
  className?: string;
}

export function HelpTooltip({ content, className }: HelpTooltipProps) {
  return (
    <Tooltip content={content} side="top">
      <span
        className={cn(
          'inline-flex items-center justify-center w-4 h-4 ml-1 text-xs text-muted-foreground hover:text-foreground cursor-help rounded-full border border-current',
          className
        )}
        tabIndex={0}
        aria-label="Help"
      >
        ?
      </span>
    </Tooltip>
  );
}
