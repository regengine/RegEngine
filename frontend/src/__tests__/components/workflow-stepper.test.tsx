/**
 * WorkflowStepper Component Tests
 *
 * Guards the contract that `completedSteps` is authoritative: a step the caller
 * omits renders as pending even when it sits left of the current step. The
 * regression this locks down is /ingest showing "01 Setup" as a filled check
 * while the same page rendered its "API Key Required" callout.
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { WorkflowStepper, WorkflowStepperInline } from '@/components/layout/workflow-stepper';

const SETUP = 'Step 1: Setup';
const INGEST = 'Step 2: Ingest';
const REVIEW = 'Step 3: Review';
const ANALYZE = 'Step 4: Analyze';

describe('WorkflowStepper', () => {
    it('renders Setup as pending when completedSteps is empty', () => {
        // The /ingest shape with no stored API key.
        render(<WorkflowStepper currentStep="ingest" completedSteps={[]} />);

        const setup = screen.getByLabelText(SETUP);
        expect(setup).toHaveTextContent('01');
        expect(setup.className).not.toContain('bg-re-text-primary');
    });

    it('renders Setup as complete when completedSteps includes it', () => {
        // The /ingest shape with a stored API key.
        render(<WorkflowStepper currentStep="ingest" completedSteps={['setup']} />);

        const setup = screen.getByLabelText(SETUP);
        expect(setup.textContent).toBe('');
        expect(setup.className).toContain('bg-re-text-primary');
    });

    it('marks the current step with aria-current and its numeral', () => {
        render(<WorkflowStepper currentStep="ingest" completedSteps={[]} />);

        const ingest = screen.getByLabelText(INGEST);
        expect(ingest).toHaveAttribute('aria-current', 'step');
        expect(ingest).toHaveTextContent('02');
        expect(screen.getByLabelText(SETUP)).not.toHaveAttribute('aria-current');
    });

    it('leaves a skipped middle step pending on a later current step', () => {
        // The /review shape when the tenant is not onboarded: setup done,
        // ingest skipped. Position must not promote ingest to complete.
        render(<WorkflowStepper currentStep="review" completedSteps={['setup']} />);

        expect(screen.getByLabelText(SETUP).textContent).toBe('');
        expect(screen.getByLabelText(INGEST)).toHaveTextContent('02');
        expect(screen.getByLabelText(REVIEW)).toHaveTextContent('03');
    });

    it('completes both prior steps on the onboarded /review shape', () => {
        render(<WorkflowStepper currentStep="review" completedSteps={['setup', 'ingest']} />);

        expect(screen.getByLabelText(SETUP).textContent).toBe('');
        expect(screen.getByLabelText(INGEST).textContent).toBe('');
        expect(screen.getByLabelText(REVIEW)).toHaveTextContent('03');
    });

    it('falls back to positional completion when completedSteps is omitted', () => {
        render(<WorkflowStepper currentStep="review" />);

        expect(screen.getByLabelText(SETUP).textContent).toBe('');
        expect(screen.getByLabelText(INGEST).textContent).toBe('');
        expect(screen.getByLabelText(REVIEW)).toHaveTextContent('03');
        expect(screen.getByLabelText(ANALYZE)).toHaveTextContent('04');
    });

    it('links every step to its destination', () => {
        render(<WorkflowStepper currentStep="ingest" completedSteps={[]} />);

        expect(screen.getByLabelText(SETUP)).toHaveAttribute('href', '/onboarding');
        expect(screen.getByLabelText(INGEST)).toHaveAttribute('href', '/ingest');
        expect(screen.getByLabelText(REVIEW)).toHaveAttribute('href', '/review');
        expect(screen.getByLabelText(ANALYZE)).toHaveAttribute('href', '/dashboard/compliance');
    });
});

describe('WorkflowStepperInline', () => {
    it('renders Setup as pending when completedSteps is empty', () => {
        render(<WorkflowStepperInline currentStep="ingest" completedSteps={[]} />);

        expect(screen.getByLabelText(SETUP).textContent).toContain('01');
    });

    it('renders Setup as complete when completedSteps includes it', () => {
        render(<WorkflowStepperInline currentStep="ingest" completedSteps={['setup']} />);

        expect(screen.getByLabelText(SETUP).textContent).not.toContain('01');
    });

    it('falls back to positional completion when completedSteps is omitted', () => {
        render(<WorkflowStepperInline currentStep="review" />);

        expect(screen.getByLabelText(SETUP).textContent).not.toContain('01');
        expect(screen.getByLabelText(INGEST).textContent).not.toContain('02');
        expect(screen.getByLabelText(REVIEW).textContent).toContain('03');
    });
});
