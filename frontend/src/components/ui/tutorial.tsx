'use client';

import React, { useState, useEffect, useLayoutEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { X, ChevronLeft, ChevronRight, Lightbulb } from 'lucide-react';
import { Button } from './button';

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

const VIEWPORT_MARGIN = 8;
const SPOTLIGHT_PADDING = 6;
const TOOLTIP_GAP = 16;

type Rect = { top: number; left: number; width: number; height: number };

function rectsDiffer(a: Rect | null, b: Rect | null) {
  if (!a || !b) return a !== b;
  return (
    Math.abs(a.top - b.top) > 0.5 ||
    Math.abs(a.left - b.left) > 0.5 ||
    Math.abs(a.width - b.width) > 0.5 ||
    Math.abs(a.height - b.height) > 0.5
  );
}

export function Tutorial({ steps, isOpen, onClose, onComplete, storageKey }: TutorialProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [targetRect, setTargetRect] = useState<Rect | null>(null);
  const [dontShowAgain, setDontShowAgain] = useState(false);
  const [tooltipSize, setTooltipSize] = useState<{ width: number; height: number } | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const step = steps[currentStep];

  // The spotlight has to follow its element through smooth scrolling, layout
  // shifts, and resizes, so the rect is re-measured on every scroll/resize
  // event rather than captured once. State only updates when the rect actually
  // moved, so the listeners are cheap.
  useEffect(() => {
    if (!isOpen || !step) return;

    let raf = 0;
    const measure = () => {
      const target = document.querySelector(step.target);
      const next = target ? target.getBoundingClientRect() : null;
      setTargetRect((prev) =>
        rectsDiffer(prev, next)
          ? next
            ? { top: next.top, left: next.left, width: next.width, height: next.height }
            : null
          : prev,
      );
    };

    const scheduleMeasure = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    };

    measure();
    document.querySelector(step.target)?.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Capture-phase scroll catches nested scroll containers, not just window.
    window.addEventListener('scroll', scheduleMeasure, { capture: true, passive: true });
    window.addEventListener('resize', scheduleMeasure);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('scroll', scheduleMeasure, { capture: true });
      window.removeEventListener('resize', scheduleMeasure);
    };
  }, [isOpen, step]);

  // The tooltip's real size feeds the positioning math; the old hardcoded
  // 320×200 estimate put long steps off-screen.
  useLayoutEffect(() => {
    if (!isOpen) return;
    const node = tooltipRef.current;
    if (!node) return;
    const { width, height } = node.getBoundingClientRect();
    setTooltipSize((prev) =>
      prev && Math.abs(prev.width - width) < 1 && Math.abs(prev.height - height) < 1
        ? prev
        : { width, height },
    );
  }, [isOpen, currentStep, targetRect]);

  // Move focus into the dialog so keyboard and screen-reader users land on the
  // step content instead of the dimmed page behind it.
  useEffect(() => {
    if (!isOpen) return;
    tooltipRef.current?.focus({ preventScroll: true });
  }, [isOpen, currentStep]);

  const handleComplete = useCallback(() => {
    if (storageKey && dontShowAgain) {
      localStorage.setItem(storageKey, 'true');
    }
    onComplete?.();
    onClose();
    setCurrentStep(0);
  }, [storageKey, dontShowAgain, onComplete, onClose]);

  const handleNext = useCallback(() => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      handleComplete();
    }
  }, [currentStep, steps.length, handleComplete]);

  const handlePrev = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  }, [currentStep]);

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
          handleNext();
          break;
        case 'Enter':
          // Let Enter activate a focused control (the action button, a nav
          // button) instead of double-firing "next" on top of the click.
          if (e.target instanceof HTMLElement && e.target.closest('button, a, input')) return;
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

  const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 1280;
  const viewportHeight = typeof window !== 'undefined' ? window.innerHeight : 800;
  const tooltipWidth = tooltipSize?.width ?? 320;
  const tooltipHeight = tooltipSize?.height ?? 220;

  const getTooltipPosition = (): { top: number; left: number } => {
    if (!targetRect) {
      return {
        top: Math.max(VIEWPORT_MARGIN, viewportHeight / 2 - tooltipHeight / 2),
        left: Math.max(VIEWPORT_MARGIN, viewportWidth / 2 - tooltipWidth / 2),
      };
    }

    const centeredLeft = targetRect.left + targetRect.width / 2 - tooltipWidth / 2;
    const centeredTop = targetRect.top + targetRect.height / 2 - tooltipHeight / 2;
    const fits = {
      top: targetRect.top - tooltipHeight - TOOLTIP_GAP >= VIEWPORT_MARGIN,
      bottom: targetRect.top + targetRect.height + TOOLTIP_GAP + tooltipHeight <= viewportHeight - VIEWPORT_MARGIN,
      left: targetRect.left - tooltipWidth - TOOLTIP_GAP >= VIEWPORT_MARGIN,
      right: targetRect.left + targetRect.width + TOOLTIP_GAP + tooltipWidth <= viewportWidth - VIEWPORT_MARGIN,
    };

    // Preferred side first, then its opposite, then below/above — whichever
    // actually fits. A side that never fits falls through to clamping.
    const preference = step.position || 'bottom';
    const order: ('top' | 'bottom' | 'left' | 'right')[] =
      preference === 'top'
        ? ['top', 'bottom', 'right', 'left']
        : preference === 'left'
          ? ['left', 'right', 'bottom', 'top']
          : preference === 'right'
            ? ['right', 'left', 'bottom', 'top']
            : ['bottom', 'top', 'right', 'left'];
    const side = order.find((candidate) => fits[candidate]) ?? preference;

    let top: number;
    let left: number;
    switch (side) {
      case 'top':
        top = targetRect.top - tooltipHeight - TOOLTIP_GAP;
        left = centeredLeft;
        break;
      case 'left':
        top = centeredTop;
        left = targetRect.left - tooltipWidth - TOOLTIP_GAP;
        break;
      case 'right':
        top = centeredTop;
        left = targetRect.left + targetRect.width + TOOLTIP_GAP;
        break;
      default:
        top = targetRect.top + targetRect.height + TOOLTIP_GAP;
        left = centeredLeft;
        break;
    }

    return {
      top: Math.min(Math.max(top, VIEWPORT_MARGIN), Math.max(VIEWPORT_MARGIN, viewportHeight - tooltipHeight - VIEWPORT_MARGIN)),
      left: Math.min(Math.max(left, VIEWPORT_MARGIN), Math.max(VIEWPORT_MARGIN, viewportWidth - tooltipWidth - VIEWPORT_MARGIN)),
    };
  };

  const hole = targetRect
    ? {
        top: Math.max(0, targetRect.top - SPOTLIGHT_PADDING),
        left: Math.max(0, targetRect.left - SPOTLIGHT_PADDING),
        width: targetRect.width + SPOTLIGHT_PADDING * 2,
        height: targetRect.height + SPOTLIGHT_PADDING * 2,
      }
    : null;

  // Four backdrop panels leave a genuine hole over the target, so the
  // spotlighted control stays fully visible AND clickable — a step can say
  // "click Run guided proof" and mean it. Clicking the dimmed area still
  // skips, matching the previous full-backdrop behavior.
  const backdropPanels = hole
    ? [
        { key: 'top', style: { top: 0, left: 0, right: 0, height: hole.top } },
        { key: 'bottom', style: { top: hole.top + hole.height, left: 0, right: 0, bottom: 0 } },
        { key: 'left', style: { top: hole.top, left: 0, width: hole.left, height: hole.height } },
        {
          key: 'right',
          style: { top: hole.top, left: hole.left + hole.width, right: 0, height: hole.height },
        },
      ]
    : [{ key: 'full', style: { top: 0, left: 0, right: 0, bottom: 0 } }];

  return (
    <>
      {backdropPanels.map((panel) => (
        <div
          key={panel.key}
          className="fixed z-[100] bg-black/50"
          style={panel.style as React.CSSProperties}
          onClick={handleSkip}
          aria-hidden
        />
      ))}

      {/* Spotlight ring around the hole */}
      {hole && (
        <div
          className="fixed z-[101] rounded-lg ring-4 ring-primary pointer-events-none"
          style={{ top: hole.top, left: hole.left, width: hole.width, height: hole.height }}
        />
      )}

      {/* Tooltip */}
      <motion.div
        ref={tooltipRef}
        role="dialog"
        aria-modal="true"
        aria-label={`${step.title} (step ${currentStep + 1} of ${steps.length})`}
        tabIndex={-1}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="fixed z-[102] w-80 max-w-[calc(100vw-16px)] rounded-xl bg-card border shadow-2xl outline-none"
        style={getTooltipPosition()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-2">
            <Lightbulb className="h-5 w-5 text-primary" />
            <span aria-live="polite" className="text-sm font-medium text-muted-foreground">
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
              <Button variant="ghost" size="sm" onClick={handlePrev} aria-label="Previous step">
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
  );
}

// Hook to check if tutorial should be shown
export function useTutorial(storageKey: string) {
  const [shouldShow, setShouldShow] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  // localStorage is browser-only, so the dismissed flag cannot be read during
  // render or SSR — the default is "hidden" until we know otherwise.
  useEffect(() => {
    const dismissed = localStorage.getItem(storageKey);
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
