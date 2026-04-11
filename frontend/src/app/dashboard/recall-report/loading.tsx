export default function Loading() {
  return (
    <div className="p-6 space-y-6 animate-pulse">
      <div className="h-8 w-48 bg-[var(--re-surface-elevated)] rounded" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-24 bg-[var(--re-surface-elevated)] rounded-xl" />
        ))}
      </div>
      <div className="h-64 bg-[var(--re-surface-elevated)] rounded-xl" />
    </div>
  );
}
