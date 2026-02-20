'use client';

import { useState, useRef } from 'react';
import Link from 'next/link';
import {
  Activity,
  Database,
  TrendingUp,
  CheckCircle,
  Zap,
  Server as ServerIcon,
  Key,
  ClipboardCheck,
  Shield,
  Book,
  User,
  LogOut,
  Settings,
  ChevronDown,
  Leaf,
  Camera,
  Clapperboard,
  Film,
  Users,
  FileText,
  Atom,
  Cpu,
  Plane,
  Car,
  Building,
  Cog,
  Gamepad2,
  Scan,
  ShieldCheck,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth-context';
import {
  useAdminHealth,
  useIngestionHealth,
  useOpportunityHealth,
  useComplianceHealth,
  useLabelsHealth,
} from '@/hooks/use-api';
import { StartTourButton } from '../onboarding/StartTourButton';
import { TenantSwitcher } from './tenant-switcher';
import { MobileNav } from './mobile-nav';

export function Header() {
  const { apiKey, clearCredentials, isOnboarded } = useAuth();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  const handleMouseEnter = (name: string) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setOpenDropdown(name);
  };

  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => {
      setOpenDropdown(null);
    }, 200);
  };

  const adminHealth = useAdminHealth();
  const ingestionHealth = useIngestionHealth();
  const opportunityHealth = useOpportunityHealth();
  const complianceHealth = useComplianceHealth();
  const labelsHealth = useLabelsHealth(); // Graph API

  const services = [
    { name: 'Admin', status: adminHealth.data?.status, isLoading: adminHealth.isLoading },
    { name: 'Ingestion', status: ingestionHealth.data?.status, isLoading: ingestionHealth.isLoading },
    { name: 'Opportunity', status: opportunityHealth.data?.status, isLoading: opportunityHealth.isLoading },
    { name: 'Compliance', status: complianceHealth.data?.status, isLoading: complianceHealth.isLoading },
    { name: 'Graph', status: labelsHealth.data?.status, isLoading: labelsHealth.isLoading },
  ];

  const unhealthyServices = services.filter(s => s.status !== 'healthy' && !s.isLoading);
  const isLoading = services.some(s => s.isLoading);
  const allHealthy = unhealthyServices.length === 0 && !isLoading;

  let statusText = 'All Systems Operational';
  let badgeVariant: 'default' | 'secondary' | 'destructive' | 'outline' = 'outline';

  if (isLoading && unhealthyServices.length === 0) {
    statusText = 'Checking...';
    badgeVariant = 'secondary';
  } else if (unhealthyServices.length > 0) {
    statusText = `${unhealthyServices.length} System(s) Unhealthy`;
    badgeVariant = 'destructive';
  }

  const handleLogout = () => {
    clearCredentials();
    setShowUserMenu(false);
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-white/80 backdrop-blur-lg dark:bg-gray-900/80">
      <div className="container flex h-16 items-center justify-between px-6">
        <div className="flex items-center gap-2 md:hidden">
          <MobileNav />
          <Link href="/" className="flex items-center space-x-2">
            <Activity className="h-6 w-6 text-primary" />
            <span className="text-xl font-bold">RegEngine</span>
          </Link>
        </div>

        <Link href="/" className="hidden md:flex items-center space-x-2 smooth-transition hover:scale-105">
          <Activity className="h-6 w-6 text-primary" />
          <span className="text-xl font-bold">RegEngine</span>
        </Link>

        <nav className="items-center space-x-1 hidden md:flex">
          {/* Data & Ingestion */}
          <DropdownMenu
            modal={false}
            open={openDropdown === 'data'}
            onOpenChange={(open) => setOpenDropdown(open ? 'data' : null)}
          >
            <DropdownMenuTrigger asChild>
              <button
                className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-accent smooth-transition focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:outline-none"
                onMouseEnter={() => handleMouseEnter('data')}
                onMouseLeave={handleMouseLeave}
              >
                <Database className="h-4 w-4 text-blue-500" />
                <span>Data</span>
                <ChevronDown className="h-3 w-3 opacity-50" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="start"
              className="w-64"
              onMouseEnter={() => handleMouseEnter('data')}
              onMouseLeave={handleMouseLeave}
            >
              <DropdownMenuLabel className="text-xs uppercase text-muted-foreground tracking-wider">Data Management</DropdownMenuLabel>
              <DropdownMenuItem asChild>
                <Link href="/ingest" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Database className="h-4 w-4 text-blue-500" />
                  <div>
                    <div className="font-medium">Ingest</div>
                    <div className="text-xs text-muted-foreground">Upload & process documents</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/review" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <ClipboardCheck className="h-4 w-4 text-emerald-500" />
                  <div>
                    <div className="font-medium">Review Queue</div>
                    <div className="text-xs text-muted-foreground">Human-in-the-loop validation</div>
                  </div>
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Compliance Suite */}
          <DropdownMenu
            modal={false}
            open={openDropdown === 'compliance'}
            onOpenChange={(open) => setOpenDropdown(open ? 'compliance' : null)}
          >
            <DropdownMenuTrigger asChild>
              <button
                className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-accent smooth-transition focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:outline-none"
                onMouseEnter={() => handleMouseEnter('compliance')}
                onMouseLeave={handleMouseLeave}
              >
                <CheckCircle className="h-4 w-4 text-emerald-500" />
                <span>Compliance</span>
                <ChevronDown className="h-3 w-3 opacity-50" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="start"
              className="w-64"
              onMouseEnter={() => handleMouseEnter('compliance')}
              onMouseLeave={handleMouseLeave}
            >
              <DropdownMenuLabel className="text-xs uppercase text-muted-foreground tracking-wider">Compliance Suite</DropdownMenuLabel>
              <DropdownMenuItem asChild>
                <Link href="/compliance" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <CheckCircle className="h-4 w-4 text-emerald-500" />
                  <div>
                    <div className="font-medium">Dashboard</div>
                    <div className="text-xs text-muted-foreground">Overall compliance view</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/compliance/status" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Shield className="h-4 w-4 text-amber-500" />
                  <div>
                    <div className="font-medium">Status</div>
                    <div className="text-xs text-muted-foreground">Real-time compliance status</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/compliance/snapshots" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Camera className="h-4 w-4 text-purple-400" />
                  <div>
                    <div className="font-medium">Snapshots</div>
                    <div className="text-xs text-muted-foreground">Point-in-time audit trail</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/controls" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Shield className="h-4 w-4 text-slate-500" />
                  <div>
                    <div className="font-medium">Controls</div>
                    <div className="text-xs text-muted-foreground">Control testing & evidence</div>
                  </div>
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>


          {/* Free Tools */}
          <DropdownMenu
            modal={false}
            open={openDropdown === 'tools'}
            onOpenChange={(open) => setOpenDropdown(open ? 'tools' : null)}
          >
            <DropdownMenuTrigger asChild>
              <button
                className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-accent smooth-transition focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:outline-none"
                onMouseEnter={() => handleMouseEnter('tools')}
                onMouseLeave={handleMouseLeave}
              >
                <Scan className="h-4 w-4 text-cyan-500" />
                <span>Tools</span>
                <ChevronDown className="h-3 w-3 opacity-50" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="start"
              className="w-64"
              onMouseEnter={() => handleMouseEnter('tools')}
              onMouseLeave={handleMouseLeave}
            >
              <DropdownMenuLabel className="text-xs uppercase text-muted-foreground tracking-wider">FSMA 204 Compliance Tools</DropdownMenuLabel>
              <DropdownMenuItem asChild>
                <Link href="/ftl-checker" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Leaf className="h-4 w-4 text-green-500" />
                  <div>
                    <div className="font-medium">FTL Checker</div>
                    <div className="text-xs text-muted-foreground">FSMA 204 Food Traceability</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/tools/exemption-qualifier" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Shield className="h-4 w-4 text-amber-500" />
                  <div>
                    <div className="font-medium">Exemption Qualifier</div>
                    <div className="text-xs text-muted-foreground">Check FSMA 204 exemption eligibility</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/tools/recall-readiness" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <ShieldCheck className="h-4 w-4 text-cyan-500" />
                  <div>
                    <div className="font-medium">Recall Readiness Score</div>
                    <div className="text-xs text-muted-foreground">Grade your 24-hour retrieval capability</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href="/tools" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Scan className="h-4 w-4 text-emerald-400" />
                  <div>
                    <div className="font-medium text-primary">View All 7 Tools →</div>
                    <div className="text-xs text-muted-foreground">Full FSMA compliance toolkit</div>
                  </div>
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>


          <DropdownMenu modal={false}>
            <DropdownMenuTrigger asChild>
              <button
                className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-accent smooth-transition focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:outline-none"
                onMouseEnter={() => handleMouseEnter('verticals')}
                onMouseLeave={handleMouseLeave}
              >
                <Activity className="h-4 w-4 text-pink-500" />
                <span>Verticals</span>
                <ChevronDown className="h-3 w-3 opacity-50" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="start"
              className="w-64 max-h-[500px] overflow-y-auto"
              onMouseEnter={() => handleMouseEnter('verticals')}
              onMouseLeave={handleMouseLeave}
            >
              <DropdownMenuLabel className="text-xs uppercase text-muted-foreground tracking-wider">Industry Frameworks</DropdownMenuLabel>
              <DropdownMenuItem asChild>
                <Link href="/verticals/aerospace" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Plane className="h-4 w-4 text-sky-500" />
                  <div>
                    <div className="font-medium">Aerospace</div>
                    <div className="text-xs text-muted-foreground">AS9100 & NADCAP</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/verticals/automotive" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Car className="h-4 w-4 text-red-500" />
                  <div>
                    <div className="font-medium">Automotive</div>
                    <div className="text-xs text-muted-foreground">IATF 16949 & PPAP</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/verticals/construction" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Building className="h-4 w-4 text-stone-500" />
                  <div>
                    <div className="font-medium">Construction</div>
                    <div className="text-xs text-muted-foreground">ISO 19650 & OSHA</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/verticals/energy" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Zap className="h-4 w-4 text-blue-500" />
                  <div>
                    <div className="font-medium">Energy</div>
                    <div className="text-xs text-muted-foreground">Grid Asset Topology</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/verticals/entertainment" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Film className="h-4 w-4 text-violet-500" />
                  <div>
                    <div className="font-medium">Entertainment (PCOS)</div>
                    <div className="text-xs text-muted-foreground">Production compliance suite</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/verticals/food-safety" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Leaf className="h-4 w-4 text-green-500" />
                  <div>
                    <div className="font-medium">Food Safety (FSMA)</div>
                    <div className="text-xs text-muted-foreground">FSMA 204 traceability</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/verticals/finance" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Key className="h-4 w-4 text-amber-500" />
                  <div>
                    <div className="font-medium">Finance</div>
                    <div className="text-xs text-muted-foreground">Reconciliation Command</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/verticals/gaming" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Gamepad2 className="h-4 w-4 text-purple-500" />
                  <div>
                    <div className="font-medium">Gaming</div>
                    <div className="text-xs text-muted-foreground">Live Risk Feed</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/verticals/healthcare" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Activity className="h-4 w-4 text-pink-500" />
                  <div>
                    <div className="font-medium">Healthcare</div>
                    <div className="text-xs text-muted-foreground">Clinical Risk Monitor</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/verticals/manufacturing" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Cog className="h-4 w-4 text-gray-500" />
                  <div>
                    <div className="font-medium">Manufacturing</div>
                    <div className="text-xs text-muted-foreground">ISO 9001 & IATF 16949</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/verticals/nuclear" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Atom className="h-4 w-4 text-orange-500" />
                  <div>
                    <div className="font-medium">Nuclear</div>
                    <div className="text-xs text-muted-foreground">NRC Compliance Evidence</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/verticals/technology" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <ServerIcon className="h-4 w-4 text-slate-500" />
                  <div>
                    <div className="font-medium">Technology</div>
                    <div className="text-xs text-muted-foreground">Trust Center</div>
                  </div>
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Opportunities */}
          <Link
            href="/opportunities"
            className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-accent smooth-transition focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            <TrendingUp className="h-4 w-4 text-orange-500" />
            <span>Opportunities</span>
          </Link>

          {/* Admin & Settings */}
          <DropdownMenu
            modal={false}
            open={openDropdown === 'admin'}
            onOpenChange={(open) => setOpenDropdown(open ? 'admin' : null)}
          >
            <DropdownMenuTrigger asChild>
              <button
                className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-accent smooth-transition focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:outline-none"
                onMouseEnter={() => handleMouseEnter('admin')}
                onMouseLeave={handleMouseLeave}
              >
                <Settings className="h-4 w-4 text-slate-500" />
                <span>Admin</span>
                <ChevronDown className="h-3 w-3 opacity-50" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="start"
              className="w-64"
              onMouseEnter={() => handleMouseEnter('admin')}
              onMouseLeave={handleMouseLeave}
            >
              <DropdownMenuLabel className="text-xs uppercase text-muted-foreground tracking-wider">Administration</DropdownMenuLabel>
              <DropdownMenuItem asChild>
                <Link href="/admin" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Key className="h-4 w-4 text-amber-500" />
                  <div>
                    <div className="font-medium">API Keys</div>
                    <div className="text-xs text-muted-foreground">Manage authentication</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/settings" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Settings className="h-4 w-4 text-slate-500" />
                  <div>
                    <div className="font-medium">Settings</div>
                    <div className="text-xs text-muted-foreground">System configuration</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href="/docs" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Book className="h-4 w-4 text-blue-400" />
                  <div>
                    <div className="font-medium">Documentation</div>
                    <div className="text-xs text-muted-foreground">API reference & guides</div>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/api-keys" className="cursor-pointer w-full flex items-center gap-3 py-2">
                  <Key className="h-4 w-4 text-orange-500" />
                  <div>
                    <div className="font-medium">API Keys</div>
                    <div className="text-xs text-muted-foreground">Generate & manage keys</div>
                  </div>
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </nav>

        <div className="hidden md:flex items-center space-x-3">
          <div className="hidden md:block">
            <TenantSwitcher />
          </div>
          <div className="hidden md:block">
            <StartTourButton />
          </div>
          {/* System Status */}
          <div title={unhealthyServices.map(s => s.name).join(', ')} className="hidden md:block">
            <Badge variant={badgeVariant}>
              {statusText}
            </Badge>
          </div>

          {/* User Menu */}
          {apiKey ? (
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">Connected</span>
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link href="/login">
                <Button variant="ghost" size="sm">Sign In</Button>
              </Link>
              <Link href="/onboarding">
                <Button size="sm">Setup</Button>
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
