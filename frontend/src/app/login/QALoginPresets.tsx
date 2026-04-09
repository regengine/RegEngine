'use client';

import { useEffect } from 'react';
import { useSearchParams } from 'next/navigation';

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

/** onApplyPreset receives the preset email directly so the parent component
 *  never needs to hold the email strings in its own bundle. */
export default function QALoginPresets({ onApplyPreset }: { onApplyPreset: (email: string) => void }) {
    const searchParams = useSearchParams();
    const presetParam = searchParams.get('preset');

    // Apply ?preset=qa / ?preset=admin from URL — handled here so the mapping
    // lives exclusively in this dynamically-loaded chunk.
    useEffect(() => {
        const preset = LOGIN_PRESETS.find((p) => p.id === presetParam);
        if (preset) {
            onApplyPreset(preset.email);
        }
    }, [presetParam, onApplyPreset]);

    return (
        <div className="space-y-2 rounded-md border border-slate-200 bg-slate-100 p-3 dark:border-slate-700 dark:bg-slate-800/50">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-300">
                QA Login Presets
            </p>
            {LOGIN_PRESETS.map((preset) => (
                <button
                    key={preset.id}
                    type="button"
                    onClick={() => onApplyPreset(preset.email)}
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
