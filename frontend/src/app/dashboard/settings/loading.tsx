export default function Loading() {
  return (
    <div className="p-6 space-y-6 animate-pulse">
      <div className="h-8 w-48 bg-[var(--re-surface-elevated)] rounded" />
      <div className="space-y-4">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-16 bg-[var(--re-surface-elevated)] rounded-xl" />
        ))}
      </div>
    </div>
  );
}
