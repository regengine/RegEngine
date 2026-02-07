'use client';

import { Button } from '@/components/ui/button';
import { HelpCircle } from 'lucide-react';
import { useDemoProgress } from './DemoProgress';

export function StartTourButton() {
    const { startDemo } = useDemoProgress();

    return (
        <Button variant="ghost" size="icon" onClick={startDemo} title="Start Demo">
            <HelpCircle className="h-5 w-5" />
            <span className="sr-only">Start Demo</span>
        </Button>
    );
}
