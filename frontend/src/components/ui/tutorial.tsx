'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronLeft, ChevronRight, Lightbulb, SkipForward } from 'lucide-react';
import { Button } from './button';
import { cn } from '@/lib/utils';

export interface TutorialStep {
  target: string; // CSS selector for target element
  title: string;
  content: string;
  position?: 'top' | 'bottom' | 'left' | 'right';
  action?: string; // Optional action button text
  onAction?: () => void;
}

interface TutorialProps {
  steps: TutorialStep[];
  isOpen: boolean;
  onClose: () => void;
  onComplete?: () => void;
  storageKey?: string; // Key to persist "don't show again" preference
}

export function Tutorial({ steps, isOpen, onClose, onComplete, storageKey }: TutorialProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const [dontShowAgain, setDontShowAgain] = useState(false);

  const step = steps[currentStep];

  // Find and highlight target element
  useEffect(() => {
    if (!isOpen || !step) return;

    const target = document.querySelector(step.target);
    if (target) {
      const rect = target.getBoundingClientRect();
      setTargetRect(rect);

      // Scroll target into view if needed
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
      setTargetRect(null);
    }
  }, [isOpen, step, currentStep]);

  const handleNext = useCallback(() => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      handleComplete();
    }
  }, [currentStep, steps.length]);

  const handlePrev = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  }, [currentStep]);

  const handleComplete = useCallback(() => {
    if (storageKey && dontShowAgain) {
      localStorage.setItem(storageKey, 'true');
    }
    onComplete?.();
    onClose();
    setCurrentStep(0);
  }, [storageKey, dontShowAgain, onComplete, onClose]);

  const handleSkip = useCallback(() => {
    if (storageKey && dontShowAgain) {
      localStorage.setItem(storageKey, 'true');
    }
    onClose();
    setCurrentStep(0);
  }, [storageKey, dontShowAgain, onClose]);

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'Escape':
          handleSkip();
          break;
        case 'ArrowRight':
        case 'Enter':
          handleNext();
          break;
        case 'ArrowLeft':
          handlePrev();
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, handleNext, handlePrev, handleSkip]);

  if (!isOpen || !step) return null;

  const getTooltipPosition = () => {
    if (!targetRect) {
      return { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' };
    }

    const padding = 16;
    const tooltipWidth = 320;
    const tooltipHeight = 200;
    const position = step.position || 'bottom';

    switch (position) {
      case 'top':
        return {
          top: targetRect.top - tooltipHeight - padding,
          left: targetRect.left + targetRect.width / 2 - tooltipWidth / 2,
        };
      case 'bottom':
        return {
          top: targetRect.bottom + padding,
          left: targetRect.left + targetRect.width / 2 - tooltipWidth / 2,
        };
      case 'left':
        return {
          top: targetRect.top + targetRect.height / 2 - tooltipHeight / 2,
          left: targetRect.left - tooltipWidth - padding,
        };
      case 'right':
        return {
          top: targetRect.top + targetRect.height / 2 - tooltipHeight / 2,
          left: targetRect.right + padding,
        };
      default:
        return {
          top: targetRect.bottom + padding,
          left: targetRect.left + targetRect.width / 2 - tooltipWidth / 2,
        };
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop overlay */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] bg-black/50"
            onClick={handleSkip}
          />

          {/* Spotlight on target element */}
          {targetRect && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed z-[101] rounded-lg ring-4 ring-primary ring-offset-4 ring-offset-background pointer-events-none"
              style={{
                top: targetRect.top - 4,
                left: targetRect.left - 4,
                width: targetRect.width + 8,
                height: targetRect.height + 8,
              }}
            />
          )}

          {/* Tooltip */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="fixed z-[102] w-80 rounded-xl bg-card border shadow-2xl"
            style={getTooltipPosition()}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b">
              <div className="flex items-center gap-2">
                <Lightbulb className="h-5 w-5 text-primary" />
                <span className="text-sm font-medium text-muted-foreground">
                  Step {currentStep + 1} of {steps.length}
                </span>
              </div>
              <button
                onClick={handleSkip}
                className="p-1 rounded-md hover:bg-muted"
                aria-label="Close tutorial"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Content */}
            <div className="p-4 space-y-3">
              <h3 className="font-semibold text-lg">{step.title}</h3>
              <p className="text-sm text-muted-foreground">{step.content}</p>

              {step.action && step.onAction && (
                <Button size="sm" onClick={step.onAction}>
                  {step.action}
                </Button>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between p-4 border-t bg-muted/50">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={dontShowAgain}
                  onChange={(e) => setDontShowAgain(e.target.checked)}
                  className="rounded"
                />
                Don&apos;t show again
              </label>

              <div className="flex items-center gap-2">
                {currentStep > 0 && (
                  <Button variant="ghost" size="sm" onClick={handlePrev}>
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                )}
                <Button size="sm" onClick={handleNext}>
                  {currentStep < steps.length - 1 ? (
                    <>
                      Next
                      <ChevronRight className="h-4 w-4 ml-1" />
                    </>
                  ) : (
                    'Finish'
                  )}
                </Button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

// Hook to check if tutorial should be shown
export function useTutorial(storageKey: string) {
  const [shouldShow, setShouldShow] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const dismissed = localStorage.getItem(storageKey);
    setShouldShow(dismissed !== 'true');
  }, [storageKey]);

  const startTutorial = useCallback(() => {
    setIsOpen(true);
  }, []);

  const closeTutorial = useCallback(() => {
    setIsOpen(false);
  }, []);

  const resetTutorial = useCallback(() => {
    localStorage.removeItem(storageKey);
    setShouldShow(true);
  }, [storageKey]);

  return {
    shouldShow,
    isOpen,
    startTutorial,
    closeTutorial,
    resetTutorial,
  };
}

// Preset tutorials for common pages
export const ingestTutorialSteps: TutorialStep[] = [
  {
    target: '[data-tutorial="api-key-input"]',
    title: 'Enter Your API Key',
    content: 'Your API key starts with "rge_". If you completed the setup wizard, it\'s already saved and will auto-fill here.',
    position: 'bottom',
  },
  {
    target: '[data-tutorial="url-input"]',
    title: 'Document URL',
    content: 'Enter a publicly accessible URL to a regulatory document. We support PDF, HTML, XML, and JSON formats.',
    position: 'bottom',
  },
  {
    target: '[data-tutorial="example-urls"]',
    title: 'Try an Example',
    content: 'Click one of these example URLs to see how the system works with real regulatory documents.',
    position: 'top',
  },
  {
    target: '[data-tutorial="submit-button"]',
    title: 'Submit for Processing',
    content: 'Click here to start the ingestion process. The document will be fetched, parsed, and entities extracted automatically.',
    position: 'top',
  },
];

export const reviewTutorialSteps: TutorialStep[] = [
  {
    target: '[data-tutorial="review-queue"]',
    title: 'Review Queue',
    content: 'Items here need human validation. They were extracted with lower confidence and require your approval.',
    position: 'bottom',
  },
  {
    target: '[data-tutorial="confidence-score"]',
    title: 'Confidence Score',
    content: 'This shows how confident the ML model was in the extraction. Lower scores need more careful review.',
    position: 'left',
  },
  {
    target: '[data-tutorial="approve-button"]',
    title: 'Approve Correct Items',
    content: 'If the extraction looks correct, click Approve to add it to the knowledge graph.',
    position: 'top',
  },
  {
    target: '[data-tutorial="reject-button"]',
    title: 'Reject Errors',
    content: 'If the extraction is incorrect, click Reject to remove it from the queue.',
    position: 'top',
  },
];
