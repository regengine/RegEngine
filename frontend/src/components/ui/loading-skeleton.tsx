/**
 * Loading Skeleton Component
 *
 * Reusable shimmer/pulse placeholder for lazy-loaded components.
 * Use as a `loading` fallback with next/dynamic or React.Suspense.
 */

import { cn } from '@/lib/utils';

interface LoadingSkeletonProps {
  /** Tailwind height class, e.g. "h-64", "h-96" */
  height?: string;
  /** Tailwind width class, defaults to "w-full" */
  width?: string;
  /** Additional class names */
  className?: string;
  /** Accessible label for screen readers */
  label?: string;
}

export function LoadingSkeleton({
  height = 'h-64',
  width = 'w-full',
  className,
  label = 'Loading content...',
}: LoadingSkeletonProps) {
  return (
    <div
      role="status"
      aria-label={label}
      className={cn(
        'animate-pulse rounded-lg bg-muted',
        height,
        width,
        className,
      )}
    >
      <span className="sr-only">{label}</span>
    </div>
  );
}

export default LoadingSkeleton;
