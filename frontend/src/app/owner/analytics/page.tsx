'use client';

import { motion } from 'framer-motion';
import { BarChart3, TrendingUp, Calendar } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export default function AnalyticsPage() {
    return (
        <div className="p-8">
            <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center justify-between mb-8"
            >
                <div>
                    <h1 className="text-3xl font-bold text-white">Analytics</h1>
                    <p className="text-white/60 mt-1">Usage trends and business insights</p>
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="outline" className="bg-white/5 border-white/10 text-white hover:bg-white/10">
                        <Calendar className="h-4 w-4 mr-2" />
                        Last 30 days
                    </Button>
                </div>
            </motion.div>

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="grid grid-cols-1 lg:grid-cols-2 gap-6"
            >
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader>
                        <CardTitle className="text-white">Documents Processed</CardTitle>
                        <CardDescription className="text-white/60">Daily document ingestion over time</CardDescription>
                    </CardHeader>
                    <CardContent className="h-64 flex items-center justify-center">
                        <div className="text-center text-white/40">
                            <BarChart3 className="h-12 w-12 mx-auto mb-4 text-amber-400/50" />
                            <p>Chart visualization coming soon</p>
                            <p className="text-sm mt-1">Integrate with your analytics provider</p>
                        </div>
                    </CardContent>
                </Card>

                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader>
                        <CardTitle className="text-white">API Usage</CardTitle>
                        <CardDescription className="text-white/60">API calls by endpoint category</CardDescription>
                    </CardHeader>
                    <CardContent className="h-64 flex items-center justify-center">
                        <div className="text-center text-white/40">
                            <TrendingUp className="h-12 w-12 mx-auto mb-4 text-amber-400/50" />
                            <p>Chart visualization coming soon</p>
                            <p className="text-sm mt-1">Integrate with your analytics provider</p>
                        </div>
                    </CardContent>
                </Card>

                <Card className="bg-white/5 backdrop-blur-xl border-white/10 lg:col-span-2">
                    <CardHeader>
                        <CardTitle className="text-white">Revenue Trends</CardTitle>
                        <CardDescription className="text-white/60">Monthly recurring revenue over time</CardDescription>
                    </CardHeader>
                    <CardContent className="h-64 flex items-center justify-center">
                        <div className="text-center text-white/40">
                            <BarChart3 className="h-12 w-12 mx-auto mb-4 text-amber-400/50" />
                            <p>Revenue chart coming soon</p>
                            <p className="text-sm mt-1">Connect to your billing system (Stripe, etc.)</p>
                        </div>
                    </CardContent>
                </Card>
            </motion.div>
        </div>
    );
}
