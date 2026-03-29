'use client';

import React, { ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { motion } from 'framer-motion';
import { LucideIcon, ChevronRight, Home, LayoutDashboard, Upload } from 'lucide-react';
import { IngestionModal } from '@/components/ingestion/IngestionModal';
import { useState } from 'react';
import { Header } from '@/components/layout/dashboard-header';
import { PageContainer } from '@/components/layout/page-container';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import Link from 'next/link';

interface VerticalDashboardLayoutProps {
    children: ReactNode;
    title: string;
    subtitle: string;
    icon: LucideIcon;
    iconColor?: string;
    iconBgColor?: string;
    systemStatus?: {
        label: string;
        variant: 'success' | 'warning' | 'error' | 'info';
        icon?: LucideIcon;
    };
    gradient?: string;
    className?: string;
}

const VERTICALS = [
    { label: 'Food Safety', value: 'food-safety' },
];

export function VerticalDashboardLayout({
    children,
    title,
    subtitle,
    icon: Icon,
    iconColor = 'text-blue-600 dark:text-blue-400',
    iconBgColor = 'bg-blue-100 dark:bg-blue-900',
    systemStatus,
    gradient = 'from-background to-muted/20',
    className,
}: VerticalDashboardLayoutProps) {
    const router = useRouter();
    const pathname = usePathname();
    const [isIngestOpen, setIsIngestOpen] = useState(false);

    // Extract current vertical from pathname
    const currentVertical = pathname?.split('/')[2] || '';

    const statusVariants = {
        success: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
        warning: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
        error: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
        info: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    };

    const handleVerticalChange = (value: string) => {
        router.push(`/verticals/${value}/dashboard`);
    };

    return (
        <div className={cn('min-h-screen bg-gradient-to-b', gradient)}>
            <Header />
            <PageContainer>
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={cn('space-y-6', className)}
                >
                    {/* Breadcrumb Navigation */}
                    <nav className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Link href="/" className="hover:text-foreground transition-colors flex items-center gap-1">
                            <Home className="w-3 h-3" />
                            Home
                        </Link>
                        <ChevronRight className="w-3 h-3" />
                        <Link href="/verticals/dashboard" className="hover:text-foreground transition-colors flex items-center gap-1">
                            <LayoutDashboard className="w-3 h-3" />
                            All Dashboards
                        </Link>
                        <ChevronRight className="w-3 h-3" />
                        <span className="text-foreground font-medium">{title}</span>
                    </nav>

                    {/* Page Header */}
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <div className={cn('p-3 rounded-lg', iconBgColor)}>
                                <Icon className={cn('h-8 w-8', iconColor)} />
                            </div>
                            <div>
                                <h1 className="text-4xl font-bold">{title}</h1>
                                <p className="text-muted-foreground mt-1">{subtitle}</p>
                            </div>
                        </div>

                        <div className="flex items-center gap-3">
                            {/* Vertical Quick Switcher */}
                            <Select value={currentVertical} onValueChange={handleVerticalChange}>
                                <SelectTrigger className="w-48">
                                    <SelectValue placeholder="Current surface" />
                                </SelectTrigger>
                                <SelectContent>
                                    {VERTICALS.map((vertical) => (
                                        <SelectItem key={vertical.value} value={vertical.value}>
                                            {vertical.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>

                            <Button variant="outline" size="sm" onClick={() => setIsIngestOpen(true)}>
                                <Upload className="h-4 w-4 mr-2" />
                                Ingest Document
                            </Button>

                            {/* System Status Badge */}
                            {systemStatus && (
                                <Badge className={statusVariants[systemStatus.variant]}>
                                    {systemStatus.icon && (
                                        <systemStatus.icon className="w-3 h-3 mr-1" />
                                    )}
                                    {systemStatus.label}
                                </Badge>
                            )}
                        </div>
                    </div>

                    {/* Dashboard Content */}
                    {children}

                    <IngestionModal
                        open={isIngestOpen}
                        onOpenChange={setIsIngestOpen}
                        vertical={title}
                    />
                </motion.div>
            </PageContainer>
        </div>
    );
}
