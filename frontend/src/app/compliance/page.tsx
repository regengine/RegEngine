'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ChecklistCardSkeleton, Skeleton } from '@/components/ui/skeleton';
import { HelpTooltip } from '@/components/ui/tooltip';
import { useChecklists, useIndustries } from '@/hooks/use-api';
import { useAuth } from '@/lib/auth-context';
import { CheckCircle, Search, Shield, Key, ArrowRight, Upload, Lightbulb } from 'lucide-react';
import { Input } from '@/components/ui/input';

export default function CompliancePage() {
  const { apiKey } = useAuth();
  const [selectedIndustry, setSelectedIndustry] = useState<string | undefined>();
  const [searchQuery, setSearchQuery] = useState('');

  const { data: industries, isLoading: industriesLoading } = useIndustries();
  const { data: checklists, isLoading: checklistsLoading } = useChecklists(selectedIndustry);

  const filteredChecklists = checklists?.filter((checklist) =>
    checklist.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    checklist.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
      <PageContainer>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {/* Page Header */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mb-8">
            <div className="p-3 rounded-lg bg-green-100 dark:bg-green-900">
              <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <h1 className="text-3xl sm:text-4xl font-bold">Compliance Checklists</h1>
              <p className="text-muted-foreground mt-1">
                Browse and validate against FSMA 204 compliance requirements
                <HelpTooltip content="Pre-built checklists help you validate your configuration against FSMA 204 traceability requirements." />
              </p>
            </div>
          </div>

          {/* No API Key Info */}
          {!apiKey && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-6"
            >
              <Card className="border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20">
                <CardContent className="pt-6">
                  <div className="flex items-start gap-3">
                    <Lightbulb className="h-5 w-5 text-blue-600 dark:text-blue-400 mt-0.5" />
                    <div className="flex-1">
                      <p className="font-medium text-blue-900 dark:text-blue-100">
                        Tip: Set up your API key
                      </p>
                      <p className="text-sm text-blue-700 dark:text-blue-300 mt-1">
                        To validate your configuration against these checklists programmatically, you&apos;ll need an API key.
                      </p>
                      <Link href="/onboarding">
                        <Button size="sm" variant="outline" className="mt-3">
                          Get Started
                          <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                      </Link>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Filters */}
          <Card className="mb-8">
            <CardContent className="pt-6">
              <div className="flex flex-col md:flex-row gap-4">
                {/* Search */}
                <div className="flex-1">
                  <div className="relative">
                    <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Search checklists..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-10"
                    />
                  </div>
                </div>

                {/* Industry Filter */}
                <div className="flex gap-2 flex-wrap">
                  <Button
                    variant={selectedIndustry === undefined ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setSelectedIndustry(undefined)}
                  >
                    All
                  </Button>
                  {industriesLoading ? (
                    <>
                      <Skeleton className="h-8 w-24" />
                      <Skeleton className="h-8 w-20" />
                      <Skeleton className="h-8 w-28" />
                    </>
                  ) : (
                    industries?.map((industry) => (
                      <Button
                        key={industry.id}
                        variant={selectedIndustry === industry.id ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setSelectedIndustry(industry.id)}
                      >
                        {industry.name}
                      </Button>
                    ))
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Checklists Grid */}
          {checklistsLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <ChecklistCardSkeleton key={i} />
              ))}
            </div>
          ) : (
            <AnimatePresence mode="wait">
              <motion.div
                key={selectedIndustry || 'all'}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
              >
                {filteredChecklists && filteredChecklists.length > 0 ? (
                  filteredChecklists.map((checklist, index) => (
                    <motion.div
                      key={checklist.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: index * 0.05 }}
                      whileHover={{ scale: 1.02 }}
                    >
                      <Card className="h-full cursor-pointer group hover:shadow-xl smooth-transition">
                        <CardHeader>
                          <div className="flex items-start justify-between mb-2">
                            <Shield className="h-8 w-8 text-primary" />
                            <Badge variant="secondary">{checklist.industry}</Badge>
                          </div>
                          <CardTitle className="group-hover:text-primary smooth-transition">
                            {checklist.name}
                          </CardTitle>
                          <CardDescription className="line-clamp-2">
                            {checklist.description}
                          </CardDescription>
                        </CardHeader>
                        <CardContent>
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-muted-foreground">
                              {checklist.items?.length || 0} requirements
                            </span>
                            <Badge variant="outline">v{checklist.version}</Badge>
                          </div>
                        </CardContent>
                      </Card>
                    </motion.div>
                  ))
                ) : (
                  <div className="col-span-full">
                    <Card className="py-12">
                      <CardContent>
                        <div className="text-center max-w-md mx-auto">
                          <div className="p-4 rounded-full bg-muted inline-block mb-4">
                            <Shield className="h-12 w-12 text-muted-foreground" />
                          </div>
                          <h3 className="text-xl font-semibold mb-2">No checklists found</h3>
                          <p className="text-muted-foreground mb-6">
                            {searchQuery
                              ? 'Try adjusting your search criteria or clearing the filter.'
                              : 'No compliance checklists available for the selected industry.'}
                          </p>

                          <div className="space-y-4">
                            {searchQuery && (
                              <Button
                                variant="outline"
                                onClick={() => setSearchQuery('')}
                              >
                                Clear Search
                              </Button>
                            )}

                            <div className="pt-4 border-t">
                              <p className="text-sm text-muted-foreground mb-3">
                                Want to add custom checklists?
                              </p>
                              <div className="flex flex-wrap justify-center gap-2">
                                <Link href="/ingest">
                                  <Button variant="outline" size="sm">
                                    <Upload className="h-4 w-4 mr-2" />
                                    Ingest Documents
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
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          )}

          {/* Info Cards */}
          <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Validation API</CardTitle>
                <CardDescription>
                  Validate your configuration against any checklist programmatically
                </CardDescription>
              </CardHeader>
              <CardContent>
                <code className="text-xs bg-muted p-2 rounded block">
                  POST /validate
                </code>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>FSMA 204 Coverage</CardTitle>
                <CardDescription>
                  Pre-built checklists and KDE templates for all 16 FDA Food Traceability List categories
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  <Badge>FSMA 204</Badge>
                  <Badge>EPCIS 2.0</Badge>
                  <Badge>GS1</Badge>
                  <Badge>FDA CTEs</Badge>
                  <Badge>KDEs</Badge>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>FSMA Workspace</CardTitle>
                <CardDescription>
                  Open advanced compliance tools for labels and traceability planning
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <Link href="/compliance/labels">
                  <Button variant="outline" className="w-full justify-start">
                    Label Compliance
                  </Button>
                </Link>
                <Link href="/compliance/traceability-plan">
                  <Button variant="outline" className="w-full justify-start">
                    Traceability Plan
                  </Button>
                </Link>
              </CardContent>
            </Card>
          </div>
        </motion.div>
      </PageContainer>
    </div>
  );
}
