"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Menu, Activity, Database, CheckCircle, Leaf, ClipboardCheck, TrendingUp, Shield, Camera, Key, Book, User, LogOut, Clapperboard, Users, FileText, Zap, Server } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"
import { cn } from "@/lib/utils"
import { useAuth } from "@/lib/auth-context"
import { TenantSwitcher } from "./tenant-switcher"

export function MobileNav() {
    const [open, setOpen] = React.useState(false)
    const { apiKey, clearCredentials } = useAuth()
    const pathname = usePathname()

    const groups = [
        {
            title: "Platform",
            items: [
                { href: "/ingest", label: "Ingest", icon: Database },
                { href: "/compliance", label: "Compliance", icon: CheckCircle },
                { href: "/fsma", label: "FSMA", icon: Leaf },
                { href: "/review", label: "Review", icon: ClipboardCheck },
                { href: "/opportunities", label: "Opportunities", icon: TrendingUp },
            ]
        },
        {
            title: "Production Compliance",
            items: [
                { href: "/pcos-assessment.html", label: "Compliance Assessment", icon: Clapperboard, iconClass: "text-purple-500" },
                { href: "/pcos-crew-import.html", label: "Crew Payroll Import", icon: Users, iconClass: "text-blue-500" },
            ]
        },
        {
            title: "Industry Frameworks",
            items: [
                { href: "/verticals/energy", label: "Energy", icon: Zap, iconClass: "text-blue-500" },
                { href: "/verticals/finance", label: "Finance", icon: Key, iconClass: "text-amber-500" },
                { href: "/verticals/gaming", label: "Gaming", icon: FileText, iconClass: "text-purple-500" },
                { href: "/verticals/healthcare", label: "Healthcare", icon: Activity, iconClass: "text-pink-500" },
                { href: "/verticals/technology", label: "Technology", icon: Server, iconClass: "text-slate-500" },
            ]
        },
        {
            title: "System",
            items: [
                { href: "/compliance/status", label: "Status", icon: Shield, iconClass: "text-amber-500" },
                { href: "/compliance/snapshots", label: "Snapshots", icon: Camera, iconClass: "text-purple-400" },
                { href: "/controls", label: "Controls", icon: Shield },
            ]
        },
        {
            title: "Resources",
            items: [
                { href: "/admin", label: "Admin", icon: Key },
                { href: "/docs", label: "Docs", icon: Book },
            ]
        }
    ]

    return (
        <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="md:hidden">
                    <Menu className="h-6 w-6" />
                    <span className="sr-only">Toggle menu</span>
                </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-[300px] sm:w-[400px] flex flex-col p-0">
                {/* Header */}
                <div className="p-6 border-b">
                    <Link href="/" className="flex items-center space-x-2" onClick={() => setOpen(false)}>
                        <Activity className="h-6 w-6 text-primary" />
                        <span className="font-bold text-xl">RegEngine</span>
                    </Link>
                    <div className="mt-4">
                        <TenantSwitcher />
                    </div>
                </div>

                {/* Scrollable Content */}
                <div className="flex-1 overflow-y-auto py-4 px-6">
                    <div className="flex flex-col gap-6">
                        {groups.map((group) => (
                            <div key={group.title} className="space-y-3">
                                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                    {group.title}
                                </h4>
                                <div className="space-y-1">
                                    {group.items.map((link) => {
                                        const isActive = pathname === link.href
                                        return (
                                            <Link
                                                key={link.href}
                                                href={link.href}
                                                className={cn(
                                                    "flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-all",
                                                    isActive
                                                        ? "bg-primary/10 text-primary"
                                                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                                )}
                                                onClick={() => setOpen(false)}
                                            >
                                                <link.icon className={cn("h-4 w-4", link.iconClass)} />
                                                {link.label}
                                            </Link>
                                        )
                                    })}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Footer / Profile */}
                <div className="border-t p-6 bg-muted/30">
                    {apiKey ? (
                        <div className="space-y-4">
                            <div className="flex items-center gap-3">
                                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                                    <User className="h-5 w-5 text-primary" />
                                </div>
                                <div className="flex-1 overflow-hidden">
                                    <p className="text-sm font-medium truncate">Authenticated User</p>
                                    <p className="text-xs text-muted-foreground truncate font-mono">
                                        {apiKey.slice(0, 12)}...
                                    </p>
                                </div>
                            </div>
                            <Button
                                variant="destructive"
                                className="w-full justify-start"
                                onClick={() => {
                                    clearCredentials();
                                    setOpen(false);
                                }}
                            >
                                <LogOut className="h-4 w-4 mr-2" />
                                Sign Out
                            </Button>
                        </div>
                    ) : (
                        <div className="grid gap-2">
                            <Link href="/login" onClick={() => setOpen(false)}>
                                <Button variant="outline" className="w-full justify-start">
                                    <Key className="h-4 w-4 mr-2" />
                                    Sign In
                                </Button>
                            </Link>
                            <Link href="/onboarding" onClick={() => setOpen(false)}>
                                <Button className="w-full justify-start">
                                    <Activity className="h-4 w-4 mr-2" />
                                    Setup (Onboarding)
                                </Button>
                            </Link>
                        </div>
                    )}
                </div>
            </SheetContent>
        </Sheet>
    )
}
