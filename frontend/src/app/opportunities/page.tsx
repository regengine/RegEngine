'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import { HelpTooltip } from '@/components/ui/tooltip';
import { WorkflowStepper } from '@/components/layout/workflow-stepper';
import { useAuth } from '@/lib/auth-context';
import { useArbitrageOpportunities, useComplianceGaps } from '@/hooks/use-api';
import { useDemoProgress } from '@/components/onboarding/DemoProgress';
import { TrendingUp, AlertTriangle, Globe, ArrowRight, Upload, Database, Lightbulb, Rocket } from 'lucide-react';
import { GapAnalysisView } from '@/components/opportunities/GapAnalysisView';

const EXAMPLE_JURISDICTIONS = [
  { j1: 'US', j2: 'EU', label: 'US vs EU' },
  { j1: 'FSMA-204', j2: 'EU-HACCP', label: 'FSMA 204 vs EU HACCP' },
  { j1: 'US', j2: 'GFSI', label: 'US vs GFSI' },
  { j1: 'US-NY', j2: 'US-CA', label: 'New York vs California' },
  { j1: 'UK', j2: 'EU', label: 'UK vs EU (Post-Brexit)' },
];

type ViewMode = 'arbitrage' | 'gaps';

export default function OpportunitiesPage() {
  const { apiKey } = useAuth();
  const { isActive: isDemoActive, currentStep, nextStep, steps } = useDemoProgress();
  const [viewMode, setViewMode] = useState<ViewMode>('arbitrage');
  const [j1, setJ1] = useState('');
  const [j2, setJ2] = useState('');
  const [concept, setConcept] = useState('');

  // Auto-select EU vs US for demo mode
  useEffect(() => {
    if (isDemoActive && !j1 && !j2) {
      setJ1('EU');
      setJ2('US-NY');
    }
  }, [isDemoActive, j1, j2]);

  const handleExampleClick = (example: { j1: string; j2: string }) => {
    setJ1(example.j1);
    setJ2(example.j2);
  };

  const { data: arbitrageData, isLoading: arbitrageLoading } = useArbitrageOpportunities({
    j1: j1 || undefined,
    j2: j2 || undefined,
    concept: concept || undefined,
    limit: 50,
  });

  const { data: gapsData, isLoading: gapsLoading } = useComplianceGaps({
    j1: j1 || undefined,
    j2: j2 || undefined,
    limit: 50,
  });

  const isLoading = viewMode === 'arbitrage' ? arbitrageLoading : gapsLoading;
  const data = viewMode === 'arbitrage' ? arbitrageData : gapsData;

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
      <PageContainer>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {/* Page Header */}
          <div className="flex items-center gap-4 mb-8">
            <div className="p-3 rounded-lg bg-purple-100 dark:bg-purple-900">
              <TrendingUp className="h-8 w-8 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <h1 className="text-4xl font-bold">Regulatory Opportunities</h1>
              <p className="text-muted-foreground mt-1">
                Discover arbitrage opportunities and compliance gaps across jurisdictions
              </p>
            </div>
          </div>

          {/* View Mode Toggle */}
          <Card className="mb-8">
            <CardContent className="pt-6">
              <div className="flex flex-col md:flex-row gap-4">
                <div className="flex gap-2">
                  <Button
                    variant={viewMode === 'arbitrage' ? 'default' : 'outline'}
                    onClick={() => setViewMode('arbitrage')}
                  >
                    <TrendingUp className="h-4 w-4 mr-2" />
                    Arbitrage Opportunities
                  </Button>
                  <Button
                    variant={viewMode === 'gaps' ? 'default' : 'outline'}
                    onClick={() => setViewMode('gaps')}
                  >
                    <AlertTriangle className="h-4 w-4 mr-2" />
                    Compliance Gaps
                  </Button>
                </div>

                <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-2">
                  <div>
                    <Input
                      placeholder="Jurisdiction 1 (e.g., US-NY)"
                      value={j1}
                      onChange={(e) => setJ1(e.target.value)}
                    />
                  </div>
                  <div>
                    <Input
                      placeholder="Jurisdiction 2 (e.g., US-CA)"
                      value={j2}
                      onChange={(e) => setJ2(e.target.value)}
                    />
                  </div>
                  {viewMode === 'arbitrage' && (
                    <Input
                      placeholder="Concept (optional)"
                      value={concept}
                      onChange={(e) => setConcept(e.target.value)}
                    />
                  )}
                </div>
              </div>

              {/* Example queries */}
              <div className="mt-4 pt-4 border-t">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm text-muted-foreground flex items-center gap-1">
                    <Lightbulb className="h-4 w-4" />
                    Try:
                  </span>
                  {EXAMPLE_JURISDICTIONS.map((example) => (
                    <Button
                      key={example.label}
                      variant="outline"
                      size="sm"
                      onClick={() => handleExampleClick(example)}
                    >
                      {example.label}
                    </Button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Results */}
          {isLoading ? (
            <div className="flex justify-center items-center py-16">
              <Spinner size="lg" />
            </div>
          ) : (
            <AnimatePresence mode="wait">
              <motion.div
                key={viewMode}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-4"
              >
                {data && data.length > 0 ? (
                  viewMode === 'arbitrage' ? (
                    // Arbitrage Opportunities
                    arbitrageData?.map((opportunity, index) => (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.05 }}
                      >
                        <Card className="card-hover">
                          <CardHeader>
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <div className="flex items-center gap-2 mb-2">
                                  <Badge variant="secondary">{opportunity.concept}</Badge>
                                  <Badge variant={opportunity.delta > 0.5 ? 'warning' : 'outline'}>
                                    Δ {opportunity.delta.toFixed(2)}
                                  </Badge>
                                </div>
                                <CardTitle className="text-xl mb-2">
                                  Regulatory Arbitrage Opportunity
                                </CardTitle>
                                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                  <Globe className="h-4 w-4" />
                                  <span>{opportunity.jurisdiction1}</span>
                                  <ArrowRight className="h-4 w-4" />
                                  <span>{opportunity.jurisdiction2}</span>
                                </div>
                              </div>
                            </div>
                          </CardHeader>
                          <CardContent>
                            <p className="text-muted-foreground">{opportunity.description}</p>
                          </CardContent>
                        </Card>
                      </motion.div>
                    ))
                  ) : (
                    // Compliance Gaps
                    <GapAnalysisView gaps={gapsData || []} j1={j1} j2={j2} />
                  )
                ) : (
                  <Card className="py-12">
                    <CardContent>
                      <div className="text-center max-w-md mx-auto">
                        <div className="p-4 rounded-full bg-muted inline-block mb-4">
                          <TrendingUp className="h-12 w-12 text-muted-foreground" />
                        </div>
                        <h3 className="text-xl font-semibold mb-2">No opportunities found</h3>
                        <p className="text-muted-foreground mb-6">
                          {j1 || j2
                            ? `No ${viewMode === 'arbitrage' ? 'arbitrage opportunities' : 'compliance gaps'} found for the selected jurisdictions.`
                            : 'Start by entering jurisdiction codes above, or try one of the example queries.'}
                        </p>

                        {/* Action buttons */}
                        <div className="space-y-4">
                          {!j1 && !j2 && (
                            <div className="flex flex-wrap justify-center gap-2">
                              {EXAMPLE_JURISDICTIONS.slice(0, 2).map((example) => (
                                <Button
                                  key={example.label}
                                  variant="outline"
                                  onClick={() => handleExampleClick(example)}
                                >
                                  Try {example.label}
                                </Button>
                              ))}
                            </div>
                          )}

                          <div className="pt-4 border-t">
                            <p className="text-sm text-muted-foreground mb-3">
                              Need more data in the system?
                            </p>
                            <div className="flex flex-wrap justify-center gap-2">
                              <Link href="/ingest">
                                <Button variant="outline" size="sm">
                                  <Upload className="h-4 w-4 mr-2" />
                                  Ingest Documents
                                </Button>
                              </Link>
                              <Link href="/compliance">
                                <Button variant="outline" size="sm">
                                  <Database className="h-4 w-4 mr-2" />
                                  Browse Checklists
                                </Button>
                              </Link>
                            </div>
                          </div>

                          {!apiKey && (
                            <div className="pt-4 border-t">
                              <p className="text-sm text-muted-foreground mb-2">
                                Haven&apos;t set up yet?
                              </p>
                              <Link href="/onboarding">
                                <Button size="sm">
                                  Start Setup Wizard
                                  <ArrowRight className="ml-2 h-4 w-4" />
                                </Button>
                              </Link>
                            </div>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </motion.div>
            </AnimatePresence>
          )}

          {/* Info Section */}
          <div className="mt-12 grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Regulatory Arbitrage</CardTitle>
                <CardDescription>
                  Identify differences in regulatory requirements across jurisdictions that could represent business opportunities
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li>• Compare requirements across jurisdictions</li>
                  <li>• Quantify regulatory deltas</li>
                  <li>• Discover cost-saving opportunities</li>
                </ul>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Compliance Gaps</CardTitle>
                <CardDescription>
                  Find areas where your compliance posture may have gaps when operating across multiple jurisdictions
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li>• Identify missing requirements</li>
                  <li>• Prioritize by severity</li>
                  <li>• Maintain compliance across regions</li>
                </ul>
              </CardContent>
            </Card>
          </div>
        </motion.div>
      </PageContainer>
    </div>
  );
}
