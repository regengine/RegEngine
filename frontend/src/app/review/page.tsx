'use client';

import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { CuratorReview } from '@/components/dashboard/curator-review';
import { WorkflowStepper } from '@/components/layout/workflow-stepper';
import { HelpTooltip } from '@/components/ui/tooltip';
import { Tutorial, useTutorial, reviewTutorialSteps } from '@/components/ui/tutorial';
import { useAuth } from '@/lib/auth-context';
import { ShieldCheck, ClipboardCheck, ArrowRight, Upload, HelpCircle } from 'lucide-react';

export default function ReviewPage() {
  const { hasAdminSession, hasTenantSession, isAuthenticated, isOnboarded } = useAuth();
  const tutorial = useTutorial('regengine-review-tutorial');
  const setupHref = isAuthenticated ? '/onboarding' : '/login';
  const setupLabel = isAuthenticated ? 'Finish Setup' : 'Sign In';

  return (
    <>
      <PageContainer>
        {/* Workflow Progress */}
        {hasTenantSession && (
          <div className="mb-6">
            <WorkflowStepper currentStep="review" completedSteps={isOnboarded ? ['setup', 'ingest'] : ['setup']} />
          </div>
        )}

        <PageHeader
          title="Curator Review"
          description="Review extracted regulatory data and validate ML extractions"
          secondaryActions={
            <Button
              variant="secondary"
              size="sm"
              onClick={tutorial.startTutorial}
              className="hidden sm:inline-flex"
            >
              <HelpCircle className="mr-2 h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              Tutorial
            </Button>
          }
        />

        {/* Review Access Warning */}
        {!hasAdminSession && (
          <Callout
            tone="warning"
            icon={ShieldCheck}
            className="mb-6"
            title="Review access required"
            action={
              <Button asChild variant="secondary" size="sm">
                <Link href={setupHref}>
                  {setupLabel}
                  <ArrowRight className="ml-2 h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                </Link>
              </Button>
            }
          >
            {isAuthenticated
              ? 'Use a workspace admin or sysadmin session to review and approve items. Finish setup or switch to an admin-capable account to continue.'
              : 'Sign in with a workspace admin or sysadmin account to review and approve items.'}
          </Callout>
        )}

        {/* Main Review Card */}
        <Card data-tutorial="review-queue">
          <CardHeader>
            <div className="min-w-0">
              <div className="flex items-center gap-1">
                <CardTitle>Review Queue</CardTitle>
                {/* PageHeader renders its description in a <p>, and Tooltip's root
                    is a <div> — so the help marker lives on the queue it explains. */}
                <HelpTooltip content="Items here were extracted with lower confidence and need human validation before being added to the knowledge graph." />
              </div>
              <CardDescription className="mt-1">
                Approve high-quality extractions and reject inaccuracies to keep the knowledge graph clean.
              </CardDescription>
            </div>
            <Badge tone="success">
              <ClipboardCheck className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
              Quality Gate
            </Badge>
          </CardHeader>
          <CardContent>
            <CuratorReview />
          </CardContent>
        </Card>

        {/* Help Cards */}
        <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Review Tips</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 text-ui text-re-text-secondary">
                <li className="flex items-start gap-2">
                  <span aria-hidden="true" className="mt-2 h-1 w-1 shrink-0 rounded-full bg-re-text-muted" />
                  Approve items where the extraction matches the source text
                </li>
                <li className="flex items-start gap-2">
                  <span aria-hidden="true" className="mt-2 h-1 w-1 shrink-0 rounded-full bg-re-text-muted" />
                  Reject items with incorrect entity types or missing context
                </li>
                <li className="flex items-start gap-2">
                  <span aria-hidden="true" className="mt-2 h-1 w-1 shrink-0 rounded-full bg-re-text-muted" />
                  Higher confidence scores generally mean more accurate extractions
                </li>
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="min-w-0">
                <CardTitle>Need More Items?</CardTitle>
                <CardDescription className="mt-1">
                  Ingest more documents to populate the review queue
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <Button asChild variant="secondary" className="w-full">
                <Link href="/ingest">
                  <Upload className="mr-2 h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                  Ingest Documents
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </PageContainer>

      {/* Tutorial */}
      <Tutorial
        steps={reviewTutorialSteps}
        isOpen={tutorial.isOpen}
        onClose={tutorial.closeTutorial}
        storageKey="regengine-review-tutorial"
      />
    </>
  );
}
