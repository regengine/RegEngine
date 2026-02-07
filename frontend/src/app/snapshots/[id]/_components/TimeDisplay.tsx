interface TimeDisplayProps {
    timestamp: string;
    format?: 'full' | 'relative' | 'iso';
}

export function TimeDisplay({ timestamp, format = 'full' }: TimeDisplayProps) {
    const date = new Date(timestamp);

    const formatDisplay = () => {
        switch (format) {
            case 'iso':
                return date.toISOString();
            case 'relative':
                return new Intl.RelativeTimeFormat('en').format(
                    Math.round((date.getTime() - Date.now()) / (1000 * 60 * 60 * 24)),
                    'day'
                );
            case 'full':
            default:
                return date.toLocaleString();
        }
    };

    return (
        <time dateTime={date.toISOString()} className="text-sm text-gray-600 dark:text-gray-400">
            {formatDisplay()}
        </time>
    );
}
