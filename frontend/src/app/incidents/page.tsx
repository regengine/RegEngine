'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';

import { DemoBanner } from '@/components/control-plane/demo-banner';
import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';

import { useAuth } from '@/lib/auth-context';
import { useQuery } from '@tanstack/react-query';

import {
  AlertTriangle,
  CheckCircle,
  Clock,
  MessageSquare,
  Plus,
  Radio,
  Shield,
  Siren,
  User,
  Zap,
} from 'lucide-react';

const INGESTION_API = '/api/ingestion';

interface IncidentAction {
  id: string;
  title: string;
  assigned_to: string;
  priority: string;
  status: string;
}

interface IncidentUpdate {
  id: string;
  timestamp: string;
  author: string;
  message: string;
  update_type: string;
}

interface Incident {
  incident_id: string;
  title: string;
  severity: string;
  incident_type: string;
  status: string;
  commander: string;
  description: string;
  affected_products: string[];
  affected_lots: string[];
  affected_facilities: string[];
  opened_at: string;
  actions: IncidentAction[];
  updates: IncidentUpdate[];
  created_at: string;
}

const SEVERITY_CONFIG: Record<string, { color: string; bgColor: string }> = {
  critical: { color: 'text-red-600', bgColor: 'bg-red-50' },
  major: { color: 'text-orange-600', bgColor: 'bg-orange-50' },
  minor: { color: 'text-amber-600', bgColor: 'bg-amber-50' },
};

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  active: { label: 'Active', color: 'bg-red-500 text-white' },
  contained: { label: 'Contained', color: 'bg-amber-500 text-white' },
  monitoring: { label: 'Monitoring', color: 'bg-blue-500 text-white' },
  resolved: { label: 'Resolved', color: 'bg-green-500 text-white' },
  closed: { label: 'Closed', color: 'bg-gray-400 text-white' },
};

const DEMO_INCIDENTS = {
  incidents: [
    {
      incident_id: 'inc-001',
      title: 'Romaine Lettuce E. coli Contamination Alert',
      severity: 'critical',
      incident_type: 'contamination',
      status: 'active',
      commander: 'sarah.chen',
      description: 'Potential E. coli contamination detected in lot ROM2026Q1-001 from Fresh Farms. FDA notification received.',
      affected_products: ['Romaine Lettuce, Whole Head', 'Romaine Lettuce, Whole Head, 24ct'],
      affected_lots: ['00614141000012ROM2026Q1-001', '00614141000012ROM2026Q1-MIX'],
      affected_facilities: ['Fresh Farms LLC', 'Sunshine Packing Co', 'Metro Distribution Center'],
      opened_at: new Date(Date.now() - 4 * 3600_000).toISOString(),
      actions: [
        { id: 'a-1', title: 'Contact Fresh Farms for harvest records', assigned_to: 'mike.johnson', priority: 'critical', status: 'completed' },
        { id: 'a-2', title: 'Pull lot ROM2026Q1-001 from Metro DC shelves', assigned_to: 'warehouse_ops', priority: 'critical', status: 'in_progress' },
        { id: 'a-3', title: 'Notify City Grocery about affected lots', assigned_to: 'sarah.chen', priority: 'high', status: 'pending' },
        { id: 'a-4', title: 'Assemble FDA response package', assigned_to: 'compliance_team', priority: 'high', status: 'pending' },
      ],
      updates: [
        { id: 'u-1', timestamp: new Date(Date.now() - 4 * 3600_000).toISOString(), author: 'sarah.chen', message: 'Incident opened: Romaine Lettuce E. coli Contamination Alert', update_type: 'progress' },
        { id: 'u-2', timestamp: new Date(Date.now() - 3 * 3600_000).toISOString(), author: 'mike.johnson', message: 'Fresh Farms confirmed harvest date 2026-03-22, Field 7A. Sending full KDE records.', update_type: 'progress' },
        { id: 'u-3', timestamp: new Date(Date.now() - 2 * 3600_000).toISOString(), author: 'sarah.chen', message: 'Forward trace complete: 2 downstream facilities identified (Metro DC, City Grocery #1247)', update_type: 'progress' },
        { id: 'u-4', timestamp: new Date(Date.now() - 1 * 3600_000).toISOString(), author: 'warehouse_ops', message: 'Metro DC pull in progress — 127 of 500 cases located and quarantined', update_type: 'progress' },
      ],
      created_at: new Date(Date.now() - 4 * 3600_000).toISOString(),
    },
    {
      incident_id: 'inc-002',
      title: 'Salmon Temperature Excursion — Pacific Seafood',
      severity: 'major',
      incident_type: 'contamination',
      status: 'contained',
      commander: 'mike.johnson',
      description: 'Temperature logger shows 2-hour excursion above 40°F during transit.',
      affected_products: ['Atlantic Salmon Fillet, 8oz'],
      affected_lots: ['00614141000043SAL2026Q1-004'],
      affected_facilities: ['Pacific Seafood Co', 'Metro Distribution Center'],
      opened_at: new Date(Date.now() - 24 * 3600_000).toISOString(),
      actions: [
        { id: 'a-5', title: 'Review temperature log data', assigned_to: 'qa_team', priority: 'high', status: 'completed' },
        { id: 'a-6', title: 'Quarantine affected lot at Metro DC', assigned_to: 'warehouse_ops', priority: 'critical', status: 'completed' },
      ],
      updates: [
        { id: 'u-5', timestamp: new Date(Date.now() - 24 * 3600_000).toISOString(), author: 'mike.johnson', message: 'Incident opened: temperature excursion detected', update_type: 'progress' },
        { id: 'u-6', timestamp: new Date(Date.now() - 20 * 3600_000).toISOString(), author: 'qa_team', message: 'Temperature exceeded 40°F for 2h 15m. Product quarantined pending lab results.', update_type: 'progress' },
        { id: 'u-7', timestamp: new Date(Date.now() - 8 * 3600_000).toISOString(), author: 'mike.johnson', message: 'Status: Contained. Lab results expected within 24h.', update_type: 'progress' },
      ],
      created_at: new Date(Date.now() - 24 * 3600_000).toISOString(),
    },
  ],
  total: 2,
};

export default function IncidentCommandPage() {
  const { apiKey, tenantId } = useAuth();
  const tid = tenantId || '';
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isDemo, setIsDemo] = useState(false);

  const incidents = useQuery({
    queryKey: ['incidents', tid],
    queryFn: async () => {
      try {
        const res = await fetch(`${INGESTION_API}/api/v1/incidents?tenant_id=${tid}`, {
          headers: { 'X-RegEngine-API-Key': apiKey || '' },
        });
        if (!res.ok) throw new Error();
        setIsDemo(false);
        return res.json();
      } catch { setIsDemo(true); return DEMO_INCIDENTS; }
    },
    refetchInterval: 10_000,
  });

  const incidentList = incidents.data?.incidents ?? [];
  const selected = (incidentList as Incident[]).find((i: Incident) => i.incident_id === selectedId);

  return (
    <PageContainer>
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Siren className="h-6 w-6 text-red-500" />
            Incident Command
          </h1>
          <p className="text-muted-foreground mt-1">
            Real-time recall coordination — actions, timeline, impact assessment
          </p>
        </div>
        <Button variant="destructive">
          <Plus className="h-4 w-4 mr-2" />
          Open Incident
        </Button>
      </div>

      <DemoBanner visible={isDemo} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Incident List */}
        <div className="space-y-3">
          {(incidentList as Incident[]).map((inc: Incident) => {
            const sevConfig = SEVERITY_CONFIG[inc.severity] || SEVERITY_CONFIG.minor;
            const statConfig = STATUS_CONFIG[inc.status] || STATUS_CONFIG.active;
            const isSelected = selectedId === inc.incident_id;
            const activeActions = inc.actions?.filter((a: IncidentAction) => a.status !== 'completed').length || 0;

            return (
              <Card
                key={inc.incident_id}
                className={`cursor-pointer transition-colors hover:border-primary/50 ${isSelected ? 'border-primary ring-1 ring-primary/20' : ''} ${inc.status === 'active' ? sevConfig.bgColor : ''}`}
                onClick={() => setSelectedId(isSelected ? null : inc.incident_id)}
              >
                <CardContent className="pt-4 pb-3">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <Badge className={statConfig.color}>{statConfig.label}</Badge>
                    <Badge variant={inc.severity === 'critical' ? 'destructive' : 'warning'}>{inc.severity}</Badge>
                  </div>
                  <h3 className="font-medium text-sm leading-tight">{inc.title}</h3>
                  <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1"><User className="h-3 w-3" />{inc.commander}</span>
                    <span className="flex items-center gap-1"><Zap className="h-3 w-3" />{activeActions} pending</span>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Detail Panel */}
        {selected ? (
          <div className="lg:col-span-2 space-y-4">
            {/* Header */}
            <Card className={selected.status === 'active' ? 'border-red-200' : ''}>
              <CardContent className="pt-5 pb-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-lg font-bold">{selected.title}</h2>
                    <p className="text-sm text-muted-foreground mt-1">{selected.description}</p>
                  </div>
                  <Badge className={STATUS_CONFIG[selected.status]?.color}>{STATUS_CONFIG[selected.status]?.label}</Badge>
                </div>
                <div className="flex flex-wrap gap-1 mt-3">
                  {selected.affected_lots?.map((lot: string) => (
                    <Badge key={lot} variant="outline" className="text-xs font-mono">{lot}</Badge>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Action Items */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Zap className="h-4 w-4 text-amber-500" />
                  Action Items ({selected.actions?.length || 0})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {(selected.actions || []).map((action: IncidentAction) => (
                    <div key={action.id} className={`flex items-center gap-3 p-2 rounded border text-sm ${action.status === 'completed' ? 'bg-green-50/50 border-green-200' : action.status === 'in_progress' ? 'bg-blue-50/50 border-blue-200' : ''}`}>
                      {action.status === 'completed' ? <CheckCircle className="h-4 w-4 text-green-500 shrink-0" /> :
                       action.status === 'in_progress' ? <Radio className="h-4 w-4 text-blue-500 shrink-0 animate-pulse" /> :
                       <Clock className="h-4 w-4 text-muted-foreground shrink-0" />}
                      <div className="flex-1 min-w-0">
                        <p className={`font-medium ${action.status === 'completed' ? 'line-through text-muted-foreground' : ''}`}>{action.title}</p>
                        <p className="text-xs text-muted-foreground">{action.assigned_to}</p>
                      </div>
                      <Badge variant={action.priority === 'critical' ? 'destructive' : 'outline'} className="text-xs shrink-0">{action.priority}</Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Timeline */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-blue-500" />
                  Timeline ({selected.updates?.length || 0})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {(selected.updates || []).reverse().map((update: IncidentUpdate) => (
                    <div key={update.id} className="flex gap-3 text-sm">
                      <div className="w-1 bg-muted rounded shrink-0" />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{update.author}</span>
                          <span className="text-xs text-muted-foreground">
                            {new Date(update.timestamp).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-muted-foreground mt-0.5">{update.message}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="lg:col-span-2">
            <Card>
              <CardContent className="py-16 text-center text-muted-foreground">
                <Siren className="h-12 w-12 mx-auto mb-3 text-gray-300" />
                <p className="font-medium">Select an incident to view details</p>
                <p className="text-sm">Click on an incident card to see actions, timeline, and impact</p>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </PageContainer>
  );
}
