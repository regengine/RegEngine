'use client';

import React from 'react';
import Link from 'next/link';
import { LucideIcon } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface QuickAction {
    label: string;
    icon: LucideIcon;
    href?: string;
    onClick?: () => void;
    variant?: 'default' | 'outline' | 'secondary' | 'ghost';
    description?: string;
    disabled?: boolean;
    external?: boolean;
}

interface QuickActionsPanelProps {
    actions: QuickAction[];
    title?: string;
    columns?: 1 | 2;
    className?: string;
}

export function QuickActionsPanel({
    actions,
    title = 'Quick Actions',
    columns = 1,
    className,
}: QuickActionsPanelProps) {
    return (
        <Card className={className}>
            <CardHeader className="pb-2">
            <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader >
        <CardContent className={cn(
            'space-y-2',
            columns === 2 && 'grid grid-cols-2 gap-2 space-y-0'
        )}>
            {actions.map((action, index) => (
                <QuickActionButton key={index} action={action} />
            ))}
        </CardContent>
    </Card >
  );
}

interface QuickActionButtonProps {
    action: QuickAction;
}

function QuickActionButton({ action }: QuickActionButtonProps) {
    const Icon = action.icon;
    const buttonContent = (
        <>
            <Icon className="w-4 h-4 mr-2" />
            <span className="flex-1 text-left">{action.label}</span>
    </>
  );

    const buttonClasses = "w-full justify-start";

    if (action.href) {
        return (
            <Link href={action.href} target={action.external ? '_blank' : undefined}>
                <Button
                    variant={action.variant || 'outline'}
                    className={buttonClasses}
                    disabled={action.disabled}
                    title={action.description}
                >
                    {buttonContent}
                </Button>
            </Link>
        );
    }

    return (
        <Button
            variant={action.variant || 'outline'}
            className={buttonClasses}
            onClick={action.onClick}
            disabled={action.disabled}
            title={action.description}
        >
            {buttonContent}
        </Button>
    );
}
