'use client';

import { motion } from 'framer-motion';
import { Shield, Key, Users, Lock, AlertTriangle, CheckCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';

const securityItems = [
    {
        title: 'API Key Management',
        description: 'Create, rotate, and revoke API keys',
        icon: Key,
        href: '/admin',
        status: 'configured'
    },
    {
        title: 'Multi-Tenant Isolation',
        description: 'Row-Level Security (RLS) enforcement',
        icon: Users,
        href: '#',
        status: 'active'
    },
    {
        title: 'Authentication',
        description: 'JWT-based auth with tenant context',
        icon: Lock,
        href: '#',
        status: 'active'
    },
    {
        title: 'Audit Logging',
        description: 'Track all admin and security events',
        icon: Shield,
        href: '#',
        status: 'configured'
    },
];

export default function SecurityPage() {
    return (
        <div className="p-8">
            <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center justify-between mb-8"
            >
                <div>
                    <h1 className="text-3xl font-bold text-white">Security</h1>
                    <p className="text-white/60 mt-1">Access controls and security settings</p>
                </div>
            </motion.div>

            {/* Security Score */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="mb-8"
            >
                <Card className="bg-gradient-to-br from-emerald-500/10 to-emerald-600/5 backdrop-blur-xl border-emerald-500/20">
                    <CardContent className="p-6 flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <div className="p-4 rounded-2xl bg-emerald-500/20">
                                <Shield className="h-8 w-8 text-emerald-400" />
                            </div>
                            <div>
                                <p className="text-white/60 text-sm">Security Score</p>
                                <p className="text-4xl font-bold text-white">98<span className="text-xl text-white/60">/100</span></p>
                            </div>
                        </div>
                        <div className="text-right">
                            <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
                                <CheckCircle className="h-3 w-3 mr-1" />
                                All checks passing
                            </Badge>
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            {/* Security Items */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="grid grid-cols-1 md:grid-cols-2 gap-4"
            >
                {securityItems.map((item) => (
                    <Card key={item.title} className="bg-white/5 backdrop-blur-xl border-white/10 hover:bg-white/10 transition-all">
                        <CardContent className="p-6">
                            <div className="flex items-start gap-4">
                                <div className="p-3 rounded-xl bg-amber-500/10">
                                    <item.icon className="h-6 w-6 text-amber-400" />
                                </div>
                                <div className="flex-1">
                                    <h3 className="font-semibold text-white mb-1">{item.title}</h3>
                                    <p className="text-sm text-white/60 mb-3">{item.description}</p>
                                    <div className="flex items-center justify-between">
                                        <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 text-xs">
                                            {item.status}
                                        </Badge>
                                        {item.href !== '#' && (
                                            <Link href={item.href}>
                                                <Button variant="ghost" size="sm" className="text-amber-400 hover:text-amber-300 hover:bg-white/5">
                                                    Manage
                                                </Button>
                                            </Link>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                ))}
            </motion.div>
        </div>
    );
}
