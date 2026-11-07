import { LiveDot } from './HueDot';

interface WorkbenchHeaderProps {
  file: string;
  checkLine: string;
}

/** Strip above a workbench table: file name on the left, check status on the right. */
export function WorkbenchHeader({ file, checkLine }: WorkbenchHeaderProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-re-border-subtle bg-re-surface-elevated px-4 py-2.5">
      <span className="truncate font-mono text-label uppercase tracking-[0.1em] text-re-text-tertiary">
        Inflow workbench · {file}
      </span>
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap font-mono text-label text-re-brand">
        <LiveDot />
        {checkLine}
      </span>
    </div>
  );
}
