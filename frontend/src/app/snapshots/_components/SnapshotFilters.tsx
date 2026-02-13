'use client';

import { useState } from 'react';
import { Search, Filter, Calendar } from 'lucide-react';

interface FilterState {
    search: string;
    status: string[];
    dateFrom: string;
    dateTo: string;
    chainStatus: string;
}

export function SnapshotFilters({ onFilterChange }: {
    onFilterChange: (filters: FilterState) => void;
}) {
    const [filters, setFilters] = useState<FilterState>({
        search: '',
        status: [],
        dateFrom: '',
        dateTo: '',
        chainStatus: 'all',
    });

    const [showFilters, setShowFilters] = useState(false);

    const handleFilterChange = (key: keyof FilterState, value: FilterState[keyof FilterState]) => {
        const newFilters = { ...filters, [key]: value };
        setFilters(newFilters);
        onFilterChange(newFilters);
    };

    const toggleStatus = (status: string) => {
        const newStatuses = filters.status.includes(status)
            ? filters.status.filter(s => s !== status)
            : [...filters.status, status];
        handleFilterChange('status', newStatuses);
    };

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 mb-6">
            {/* Search Bar */}
            <div className="flex gap-4 items-center">
                <div className="flex-1 relative">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <input
                        type="text"
                        placeholder="Search by ID, facility name, or hash..."
                        value={filters.search}
                        onChange={(e) => handleFilterChange('search', e.target.value)}
                        className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                    />
                </div>
                <button
                    onClick={() => setShowFilters(!showFilters)}
                    className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-2"
                >
                    <Filter className="h-5 w-5" />
                    Filters
                </button>
            </div>

            {/* Advanced Filters */}
            {showFilters && (
                <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* Status Filter */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Status
                        </label>
                        <div className="space-y-2">
                            {['NOMINAL', 'DEGRADED', 'NON_COMPLIANT'].map((status) => (
                                <label key={status} className="flex items-center">
                                    <input
                                        type="checkbox"
                                        checked={filters.status.includes(status)}
                                        onChange={() => toggleStatus(status)}
                                        className="mr-2 h-4 w-4 text-blue-600 rounded focus:ring-blue-500"
                                    />
                                    <span className="text-sm text-gray-700 dark:text-gray-300">{status}</span>
                                </label>
                            ))}
                        </div>
                    </div>

                    {/* Date Range */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Date Range
                        </label>
                        <div className="space-y-2">
                            <input
                                type="date"
                                value={filters.dateFrom}
                                onChange={(e) => handleFilterChange('dateFrom', e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                            />
                            <input
                                type="date"
                                value={filters.dateTo}
                                onChange={(e) => handleFilterChange('dateTo', e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                            />
                        </div>
                    </div>

                    {/* Chain Status */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Chain Status
                        </label>
                        <select
                            value={filters.chainStatus}
                            onChange={(e) => handleFilterChange('chainStatus', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                        >
                            <option value="all">All</option>
                            <option value="genesis">Genesis Only</option>
                            <option value="linked">Has Predecessor</option>
                            <option value="broken">Broken Chain</option>
                        </select>
                    </div>
                </div>
            )}

            {/* Active Filters Display */}
            {(filters.status.length > 0 || filters.search || filters.dateFrom || filters.dateTo) && (
                <div className="mt-4 flex flex-wrap gap-2">
                    {filters.search && (
                        <span className="px-3 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full text-sm">
                            Search: "{filters.search}"
                        </span>
                    )}
                    {filters.status.map((status) => (
                        <span
                            key={status}
                            className="px-3 py-1 bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-full text-sm"
                        >
                            {status}
                        </span>
                    ))}
                    {filters.dateFrom && (
                        <span className="px-3 py-1 bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200 rounded-full text-sm">
                            From: {filters.dateFrom}
                        </span>
                    )}
                </div>
            )}
        </div>
    );
}
