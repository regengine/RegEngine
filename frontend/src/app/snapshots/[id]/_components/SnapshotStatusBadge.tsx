interface SnapshotStatusBadgeProps {
    status: 'NOMINAL' | 'DEGRADED' | 'NON_COMPLIANT';
}

export function SnapshotStatusBadge({ status }: SnapshotStatusBadgeProps) {
    const styles = {
        NOMINAL: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
        DEGRADED: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
        NON_COMPLIANT: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    };

    return (
        <span className={`px-3 py-1 rounded-full text-sm font-medium ${styles[status]}`}>
            {status.replace('_', ' ')}
        </span>
    );
}
