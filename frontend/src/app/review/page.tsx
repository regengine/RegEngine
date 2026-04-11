'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { CuratorReview } from '@/components/dashboard/curator-review';
import { WorkflowStepper } from '@/components/layout/workflow-stepper';
import { HelpTooltip } from '@/components/ui/tooltip';
import { Tutorial, useTutorial, reviewTutorialSteps } from '@/components/ui/tutorial';
import { useAuth } from '@/lib/auth-context';
import { ShieldCheck, ClipboardCheck, Lightbulb, ArrowRight, Key, Upload, HelpCircle } from 'lucide-react';

export default function ReviewPage() {
  const { apiKey, isOnboarded } = useAuth();
  const tutorial = useTutorial('regengine-review-tutorial');

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
      <PageContainer>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="max-w-5xl mx-auto space-y-6"
        >
          {/* Workflow Progress */}
          {apiKey && (
            <div className="mb-6">
              <WorkflowStepper currentStep="review" completedSteps={isOnboarded ? ['setup', 'ingest'] : ['setup']} />
            </div>
          )}

          {/* Page Header */}
          <div className="flex items-center gap-4 mb-6">
            <div className="p-3 rounded-lg bg-re-warning-muted dark:bg-re-warning">
              <ClipboardCheck className="h-8 w-8 text-re-warning dark:text-re-warning" />
            </div>
            <div className="flex-1">
              <h1 className="text-4xl font-bold">Curator Review</h1>
              <p className="text-muted-foreground mt-1">
                Review extracted regulatory data and validate ML extractions
                <HelpTooltip content="Items here were extracted with lower confidence and need human validation before being added to the knowledge graph." />
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={tutorial.startTutorial}
              className="hidden sm:flex"
            >
              <HelpCircle className="h-4 w-4 mr-2" />
              Tutorial
            </Button>
          </div>

          {/* No API Key Warning */}
          {!apiKey && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <Card className="border-re-warning dark:border-re-warning bg-re-warning-muted dark:bg-re-warning/20">
                <CardContent className="pt-6">
                  <div className="flex items-start gap-3">
                    <Key className="h-5 w-5 text-re-warning dark:text-re-warning mt-0.5" />
                    <div className="flex-1">
                      <p className="font-medium text-re-warning dark:text-re-warning">
                        API Key Required
                      </p>
                      <p className="text-sm text-re-warning dark:text-re-warning mt-1">
                        You need an API key to review and approve items. Complete the setup wizard to get started.
                      </p>
                      <Link href="/onboarding">
                        <Button size="sm" variant="outline" className="mt-3">
                          Go to Setup
                          <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                      </Link>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Main Review Card */}
          <Card data-tutorial="review-queue">
            <CardHeader className="flex flex-row items-start justify-between gap-4">
              <div className="space-y-2">
                <CardTitle className="text-2xl font-bold">Review Queue</CardTitle>
                <CardDescription>
                  Approve high-quality extractions and reject inaccuracies to keep the knowledge graph clean.
                </CardDescription>
              </div>
              <div className="p-3 rounded-lg bg-re-success-muted dark:bg-re-success/30 text-re-success dark:text-re-success border border-green-200 dark:border-green-800">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <ShieldCheck className="h-4 w-4" />
                  Quality Gate
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <CuratorReview />
            </CardContent>
          </Card>

          {/* Help Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Lightbulb className="h-5 w-5 text-re-warning" />
                  Review Tips
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <span className="text-re-success mt-1">•</span>
                    Approve items where the extraction matches the source text
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-re-danger mt-1">•</span>
                    Reject items with incorrect entity types or missing context
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-re-info mt-1">•</span>
                    Higher confidence scores generally mean more accurate extractions
                  </li>
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Need More Items?</CardTitle>
                <CardDescription>
                  Ingest more documents to populate the review queue
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Link href="/ingest">
                  <Button variant="outline" className="w-full">
                    <Upload className="h-4 w-4 mr-2" />
                    Ingest Documents
                  </Button>
                </Link>
              </CardContent>
            </Card>
          </div>
        </motion.div>
      </PageContainer>      {/* Tutorial */}
      <Tutorial
        steps={reviewTutorialSteps}
        isOpen={tutorial.isOpen}
        onClose={tutorial.closeTutorial}
        storageKey="regengine-review-tutorial"
      />
    </div>
  );
}
