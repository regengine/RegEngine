'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { Code, BookOpen, Zap, FileCode } from 'lucide-react';

export type VerticalTab = 'overview' | 'api' | 'quickstart' | 'examples';

interface VerticalTabsProps {
    activeTab: VerticalTab;
    onTabChange: (tab: VerticalTab) => void;
    colorScheme?: 'blue' | 'orange' | 'emerald' | 'purple' | 'red' | 'amber' | 'sky' | 'gray';
}

const colorClasses = {
    blue: {
        active: 'bg-blue-600 text-white',
        hover: 'hover:bg-blue-50 dark:hover:bg-blue-900/20',
        border: 'border-blue-600',
        text: 'text-blue-600 dark:text-blue-400',
    },
    orange: {
        active: 'bg-orange-600 text-white',
        hover: 'hover:bg-orange-50 dark:hover:bg-orange-900/20',
        border: 'border-orange-600',
        text: 'text-orange-600 dark:text-orange-400',
    },
    emerald: {
        active: 'bg-emerald-600 text-white',
        hover: 'hover:bg-emerald-50 dark:hover:bg-emerald-900/20',
        border: 'border-emerald-600',
        text: 'text-emerald-600 dark:text-emerald-400',
    },
    purple: {
        active: 'bg-purple-600 text-white',
        hover: 'hover:bg-purple-50 dark:hover:bg-purple-900/20',
        border: 'border-purple-600',
        text: 'text-purple-600 dark:text-purple-400',
    },
    red: {
        active: 'bg-red-600 text-white',
        hover: 'hover:bg-red-50 dark:hover:bg-red-900/20',
        border: 'border-red-600',
        text: 'text-red-600 dark:text-red-400',
    },
    amber: {
        active: 'bg-amber-600 text-white',
        hover: 'hover:bg-amber-50 dark:hover:bg-amber-900/20',
        border: 'border-amber-600',
        text: 'text-amber-600 dark:text-amber-400',
    },
    sky: {
        active: 'bg-sky-600 text-white',
        hover: 'hover:bg-sky-50 dark:hover:bg-sky-900/20',
        border: 'border-sky-600',
        text: 'text-sky-600 dark:text-sky-400',
    },
    gray: {
        active: 'bg-gray-600 text-white',
        hover: 'hover:bg-gray-50 dark:hover:bg-gray-900/20',
        border: 'border-gray-600',
        text: 'text-gray-600 dark:text-gray-400',
    },
};

const tabs = [
    { id: 'overview' as const, label: 'Overview', icon: BookOpen },
    { id: 'api' as const, label: 'API Reference', icon: Code },
    { id: 'quickstart' as const, label: 'Quickstart', icon: Zap },
    { id: 'examples' as const, label: 'Examples', icon: FileCode },
];

export function VerticalTabs({
    activeTab,
    onTabChange,
    colorScheme = 'blue',
}: VerticalTabsProps) {
    const colors = colorClasses[colorScheme];

    return (
        <div className="border-b border-gray-200 dark:border-gray-800 mb-8">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <nav className="flex gap-2 overflow-x-auto scrollbar-hide -mb-px">
                    {tabs.map((tab) => {
                        const Icon = tab.icon;
                        const isActive = activeTab === tab.id;

                        return (
                            <button
                                key={tab.id}
                                onClick={() => onTabChange(tab.id)}
                                className={`
                                    relative px-6 py-4 font-semibold text-sm whitespace-nowrap
                                    transition-colors duration-200
                                    ${isActive
                                        ? colors.text
                                        : 'text-gray-600 dark:text-gray-400'
                                    }
                                    ${!isActive && colors.hover}
                                    focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-${colorScheme}-500
                                `}
                            >
                                <div className="flex items-center gap-2">
                                    <Icon className="h-4 w-4" />
                                    {tab.label}
                                </div>

                                {isActive && (
                                    <motion.div
                                        layoutId={`tab-indicator-${colorScheme}`}
                                        className={`absolute bottom-0 left-0 right-0 h-0.5 ${colors.active}`}
                                        transition={{
                                            type: 'spring',
                                            stiffness: 500,
                                            damping: 30,
                                        }}
                                    />
                                )}
                            </button>
                        );
                    })}
                </nav>
            </div>
        </div>
    );
}
