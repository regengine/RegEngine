'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { FileText, Users, MapPin, Phone } from 'lucide-react';

/**
 * FSMA 204 Traceability Plan Page
 * 
 * Placeholder UI for viewing and managing facility traceability plans.
 * This page will integrate with the backend traceability plan API.
 */
export default function TraceabilityPlanPage() {
  const [selectedTab, setSelectedTab] = useState<'overview' | 'procedures' | 'contacts'>('overview');

  // Placeholder data - in production, this would come from the API
  const planData = {
    facilityName: 'Fresh Foods Processing Inc.',
    planVersion: '1.0',
    effectiveDate: '2025-01-20',
    lastUpdated: '2025-12-01',
    status: 'Active',
    procedures: 4,
    contacts: 2,
    recordTypes: 5,
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
      <PageContainer>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {/* Page Header */}
          <div className="flex items-center gap-4 mb-8">
            <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-900">
              <FileText className="h-8 w-8 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h1 className="text-4xl font-bold">Traceability Plan</h1>
              <p className="text-muted-foreground mt-1">
                FSMA 204 traceability plan management for {planData.facilityName}
              </p>
            </div>
          </div>

          {/* Status Card */}
          <Card className="mb-8">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Plan Status</CardTitle>
                <Badge variant="default" className="bg-green-500">
                  {planData.status}
                </Badge>
              </div>
              <CardDescription>
                Version {planData.planVersion} | Effective: {planData.effectiveDate}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
                  <FileText className="h-8 w-8 text-primary" />
                  <div>
                    <p className="text-2xl font-bold">{planData.procedures}</p>
                    <p className="text-sm text-muted-foreground">Procedures</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
                  <Users className="h-8 w-8 text-primary" />
                  <div>
                    <p className="text-2xl font-bold">{planData.contacts}</p>
                    <p className="text-sm text-muted-foreground">Contacts</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50">
                  <MapPin className="h-8 w-8 text-primary" />
                  <div>
                    <p className="text-2xl font-bold">{planData.recordTypes}</p>
                    <p className="text-sm text-muted-foreground">Record Types</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Tabs */}
          <div className="flex gap-2 mb-6">
            {(['overview', 'procedures', 'contacts'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setSelectedTab(tab)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${selectedTab === tab
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted hover:bg-muted/80'
                  }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>

          {/* Content */}
          {selectedTab === 'overview' && (
            <Card>
              <CardHeader>
                <CardTitle>Plan Overview</CardTitle>
                <CardDescription>
                  Summary of FSMA 204 traceability plan requirements
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="p-4 rounded-lg border">
                    <h4 className="font-medium mb-2">FDA Required Elements</h4>
                    <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
                      <li>Description of procedures for maintaining traceability records</li>
                      <li>Description of records maintained</li>
                      <li>Point(s) of contact available 24/7</li>
                      <li>Supply chain map (optional but recommended)</li>
                    </ul>
                  </div>
                  <div className="p-4 rounded-lg border">
                    <h4 className="font-medium mb-2">Compliance Status</h4>
                    <p className="text-sm text-muted-foreground">
                      Your traceability plan meets FDA requirements for FSMA 204.
                      Next review date: {planData.lastUpdated}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {selectedTab === 'procedures' && (
            <Card>
              <CardHeader>
                <CardTitle>Procedures</CardTitle>
                <CardDescription>
                  Documented procedures for maintaining traceability records
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Procedure management interface coming soon.
                </p>
              </CardContent>
            </Card>
          )}

          {selectedTab === 'contacts' && (
            <Card>
              <CardHeader>
                <CardTitle>24/7 Contacts</CardTitle>
                <CardDescription>
                  Points of contact for FDA traceability inquiries
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex items-center gap-4 p-4 rounded-lg border">
                    <Phone className="h-6 w-6 text-primary" />
                    <div>
                      <p className="font-medium">Food Safety Director</p>
                      <p className="text-sm text-muted-foreground">Primary Contact</p>
                      <p className="text-sm text-muted-foreground">555-123-4567 (24/7)</p>
                    </div>
                    <Badge variant="outline" className="ml-auto">24/7</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </motion.div>
      </PageContainer>
    </div>
  );
}
