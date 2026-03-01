'use client';

import { motion } from 'framer-motion';
import { Settings, Building2, Palette, Bell, Globe, CreditCard } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export default function SettingsPage() {
    return (
        <div className="p-8">
            <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center justify-between mb-8"
            >
                <div>
                    <h1 className="text-3xl font-bold text-white">Settings</h1>
                    <p className="text-white/60 mt-1">Platform configuration and preferences</p>
                </div>
            </motion.div>

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="space-y-6 max-w-2xl"
            >
                {/* Company Settings */}
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader>
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-amber-500/10">
                                <Building2 className="h-5 w-5 text-amber-400" />
                            </div>
                            <div>
                                <CardTitle className="text-white">Company Details</CardTitle>
                                <CardDescription className="text-white/60">Your organization information</CardDescription>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-2">
                            <Label className="text-white/80">Company Name</Label>
                            <Input
                                defaultValue="RegEngine Inc."
                                className="bg-white/5 border-white/10 text-white"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-white/80">Support Email</Label>
                            <Input
                                defaultValue="support@regengine.co"
                                className="bg-white/5 border-white/10 text-white"
                            />
                        </div>
                        <Button className="bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-white">
                            Save Changes
                        </Button>
                    </CardContent>
                </Card>

                {/* Branding */}
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader>
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-amber-500/10">
                                <Palette className="h-5 w-5 text-amber-400" />
                            </div>
                            <div>
                                <CardTitle className="text-white">Branding</CardTitle>
                                <CardDescription className="text-white/60">Customize appearance for white-label</CardDescription>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <p className="text-white/40 text-sm">
                            White-label customization is available through enterprise onboarding.
                            Contact the platform team to configure branded domains and theme presets.
                        </p>
                    </CardContent>
                </Card>

                {/* Notifications */}
                <Card className="bg-white/5 backdrop-blur-xl border-white/10">
                    <CardHeader>
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-amber-500/10">
                                <Bell className="h-5 w-5 text-amber-400" />
                            </div>
                            <div>
                                <CardTitle className="text-white">Notifications</CardTitle>
                                <CardDescription className="text-white/60">Alert preferences</CardDescription>
                            </div>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <p className="text-white/40 text-sm">
                            Notification routing is managed from tenant and user settings.
                            Use owner alerts to monitor billing, security, and lifecycle events.
                        </p>
                    </CardContent>
                </Card>
            </motion.div>
        </div>
    );
}
