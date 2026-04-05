'use client';

const LOGIN_PRESETS = [
    {
        id: 'qa' as const,
        label: 'QA Tester',
        email: 'test@example.com',
        access: 'Dashboard and core user flows',
    },
    {
        id: 'admin' as const,
        label: 'QA Admin',
        email: 'admin@example.com',
        access: 'Sysadmin and admin access checks',
    },
];

export type LoginPreset = (typeof LOGIN_PRESETS)[number]['id'];

export default function QALoginPresets({ onApplyPreset }: { onApplyPreset: (presetId: LoginPreset) => void }) {
    return (
        <div className="space-y-2 rounded-md border border-slate-200 bg-slate-100 p-3 dark:border-slate-700 dark:bg-slate-800/50">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-300">
                QA Login Presets
            </p>
            {LOGIN_PRESETS.map((preset) => (
                <button
                    key={preset.id}
                    type="button"
                    onClick={() => onApplyPreset(preset.id)}
                    className="w-full rounded border border-slate-200 bg-white p-2 text-left transition-colors hover:border-primary/50 dark:border-slate-700 dark:bg-slate-900"
                >
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{preset.label}</p>
                    <p className="text-xs text-slate-600 dark:text-slate-400">{preset.access}</p>
                    <p className="mt-1 text-xs font-mono text-slate-700 dark:text-slate-300">
                        {preset.email}
                    </p>
                </button>
            ))}
            <p className="text-[11px] text-slate-600 dark:text-slate-400">
                Passwords are managed outside client source.
            </p>
        </div>
    );
}
