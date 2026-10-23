import { TimedSkeleton } from '@/components/ui/timed-skeleton';

export default function Loading() {
  return (
    <TimedSkeleton className="p-6" errorMessage="The integrations page did not finish loading. Reload to try again.">
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-48 bg-[var(--re-surface-elevated)] rounded" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-24 bg-[var(--re-surface-elevated)] rounded-xl" />
          ))}
        </div>
        <div className="h-64 bg-[var(--re-surface-elevated)] rounded-xl" />
      </div>
    </TimedSkeleton>
  );
}
