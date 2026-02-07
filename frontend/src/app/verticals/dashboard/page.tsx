'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import {
    Zap, Atom, DollarSign, Server, Heart, Factory, Car, Plane, Hammer, Gamepad2,
    Activity, AlertCircle, TrendingUp, TrendingDown, ArrowRight, RefreshCw,
    CheckCircle2, AlertTriangle, XCircle
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useVerticalSummaries, useSystemOverview } from './api';

// Icon mapping
const iconMap: Record<string, any> = {
    Zap, Atom, DollarSign, Server, Heart, Factory, Car, Plane, Hammer, Gamepad2
};

export default function DashboardIndexPage() {
    const [isRefreshing, setIsRefreshing] = useState(false);
    const { data: verticals, isLoading: verticalsLoading, refetch: refetchVerticals } = useVerticalSummaries();
    const { data: overview, isLoading: overviewLoading } = useSystemOverview();

    const handleRefresh = async () => {
        setIsRefreshing(true);
        await refetchVerticals();
        setTimeout(() => setIsRefreshing(false), 1000);
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800">
            {/* Header */}
            <div className="border-b bg-white dark:bg-gray-800">
                <div className="container mx-auto px-6 py-6">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Compliance Dashboard</h1>
                            <p className="text-muted-foreground mt-1">Monitor all industry vertical compliance in one place</p>
                        </div>
                        <Button
                            onClick={handleRefresh}
                            disabled={isRefreshing}
                            variant="outline"
                            className="flex items-center gap-2"
                        >
                            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                            Refresh
                        </Button>
                    </div>
                </div>
            </div>

            <div className="container mx-auto px-6 py-8">
                {/* System Overview */}
                {overviewLoading ? (
                    <Card className="mb-8">
                        <CardContent className="p-6">
                            <Skeleton className="h-24 w-full" />
                        </CardContent>
                    </Card>
                ) : overview && (
                    <Card className="mb-8 border-2">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Activity className="w-5 h-5" />
                                System Overview
                            </CardTitle>
                            <CardDescription>Last updated: {new Date(overview.lastSystemCheck).toLocaleString()}</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-2 md:grid-cols-6 gap-6">
                                <div className="text-center">
                                    <div className="text-4xl font-bold text-green-600 dark:text-green-400">{overview.overallScore}</div>
                                    <div className="text-sm text-muted-foreground mt-1">Overall Score</div>
                                </div>
                                <div className="text-center">
                                    <div className="text-4xl font-bold text-gray-900 dark:text-white">{overview.totalVerticals}</div>
                                    <div className="text-sm text-muted-foreground mt-1">Verticals</div>
                                </div>
                                <div className="text-center">
                                    <div className="text-4xl font-bold text-green-600 dark:text-green-400 flex items-center justify-center gap-1">
                                        <CheckCircle2 className="w-8 h-8" />
                                        {overview.healthyVerticals}
                                    </div>
                                    <div className="text-sm text-muted-foreground mt-1">Healthy</div>
                                </div>
                                <div className="text-center">
                                    <div className="text-4xl font-bold text-amber-600 dark:text-amber-400 flex items-center justify-center gap-1">
                                        <AlertTriangle className="w-8 h-8" />
                                        {overview.warningVerticals}
                                    </div>
                                    <div className="text-sm text-muted-foreground mt-1">Warning</div>
                                </div>
                                <div className="text-center">
                                    <div className="text-4xl font-bold text-red-600 dark:text-red-400 flex items-center justify-center gap-1">
                                        <XCircle className="w-8 h-8" />
                                        {overview.criticalVerticals}
                                    </div>
                                    <div className="text-sm text-muted-foreground mt-1">Critical</div>
                                </div>
                                <div className="text-center">
                                    <div className="text-4xl font-bold text-blue-600 dark:text-blue-400">{overview.totalAlerts}</div>
                                    <div className="text-sm text-muted-foreground mt-1">Active Alerts</div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Vertical Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                    {verticalsLoading ? (
                        [...Array(10)].map((_, i) => (
                            <Card key={i}>
                                <CardContent className="p-6">
                                    <Skeleton className="h-48 w-full" />
                                </CardContent>
                            </Card>
                        ))
                    ) : (
                        verticals?.map((vertical) => {
                            const Icon = iconMap[vertical.icon];
                            const statusColor =
                                vertical.status === 'healthy' ? 'text-green-600' :
                                    vertical.status === 'warning' ? 'text-amber-600' :
                                        'text-red-600';

                            return (
                                <Link key={vertical.id} href={`/verticals/${vertical.slug}/dashboard`}>
                                    <Card className="hover:shadow-lg transition-all cursor-pointer group h-full">
                                        <CardHeader>
                                            <div className="flex items-start justify-between mb-2">
                                                <div className={`p-3 rounded-lg ${vertical.iconBgColor} dark:bg-opacity-20`}>
                                                    <Icon className={`w-6 h-6 ${vertical.iconColor}`} />
                                                </div>
                                                <Badge variant={vertical.status === 'healthy' ? 'default' : vertical.status === 'warning' ? 'secondary' : 'destructive'} className="text-xs">
                                                    {vertical.status}
                                                </Badge>
                                            </div>
                                            <CardTitle className="text-lg">{vertical.name}</CardTitle>
                                            <CardDescription className="text-xs">{vertical.primaryStandard}</CardDescription>
                                        </CardHeader>
                                        <CardContent>
                                            {/* Compliance Score */}
                                            <div className="mb-4">
                                                <div className="flex items-baseline gap-2 mb-1">
                                                    <span className="text-3xl font-bold text-gray-900 dark:text-white">{vertical.complianceScore}</span>
                                                    <span className="text-sm text-muted-foreground">/100</span>
                                                    {vertical.scoreChange !== 0 && (
                                                        <div className={`flex items-center gap-1 text-xs ${vertical.scoreChange > 0 ? 'text-green-600' : 'text-red-600'}`}>
                                                            {vertical.scoreChange > 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                                                            {Math.abs(vertical.scoreChange)}%
                                                        </div>
                                                    )}
                                                </div>
                                                <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                                    <div
                                                        className={`h-full ${vertical.complianceScore >= 95 ? 'bg-green-500' : vertical.complianceScore >= 85 ? 'bg-amber-500' : 'bg-red-500'}`}
                                                        style={{ width: `${vertical.complianceScore}%` }}
                                                    />
                                                </div>
                                            </div>

                                            {/* Quick Stats */}
                                            <div className="space-y-2 mb-4">
                                                {vertical.quickStats.map((stat, idx) => (
                                                    <div key={idx} className="flex items-center justify-between text-sm">
                                                        <span className="text-muted-foreground">{stat.label}</span>
                                                        <span className="font-semibold text-gray-900 dark:text-white">{stat.value}</span>
                                                    </div>
                                                ))}
                                            </div>

                                            {/* Alerts */}
                                            {vertical.activeAlerts > 0 && (
                                                <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400 mb-4">
                                                    <AlertCircle className="w-3 h-3" />
                                                    {vertical.activeAlerts} active alert{vertical.activeAlerts > 1 ? 's' : ''}
                                                </div>
                                            )}

                                            {/* Last Updated */}
                                            <div className="text-xs text-muted-foreground mb-3">
                                                Updated {new Date(vertical.lastUpdated).toLocaleString('en-US', {
                                                    month: 'short',
                                                    day: 'numeric',
                                                    hour: '2-digit',
                                                    minute: '2-digit'
                                                })}
                                            </div>

                                            {/* View Dashboard Link */}
                                            <Button variant="ghost" className="w-full justify-between group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                                                View Dashboard
                                                <ArrowRight className="w-4 h-4" />
                                            </Button>
                                        </CardContent>
                                    </Card>
                                </Link>
                            );
                        })
                    )}
                </div>
            </div>
        </div>
    );
}
