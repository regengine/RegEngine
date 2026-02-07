'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, PartyPopper, ArrowRight, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import confetti from 'canvas-confetti';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

interface DemoCompletionModalProps {
    isOpen: boolean;
    onClose: () => void;
    onRestart: () => void;
}

export function DemoCompletionModal({ isOpen, onClose, onRestart }: DemoCompletionModalProps) {
    const router = useRouter();

    useEffect(() => {
        if (isOpen) {
            // Fire confetti
            const duration = 3 * 1000;
            const animationEnd = Date.now() + duration;
            const defaults = { startVelocity: 30, spread: 360, ticks: 60, zIndex: 9999 };

            const randomInRange = (min: number, max: number) => Math.random() * (max - min) + min;

            const interval: any = setInterval(function () {
                const timeLeft = animationEnd - Date.now();

                if (timeLeft <= 0) {
                    return clearInterval(interval);
                }

                const particleCount = 50 * (timeLeft / duration);
                confetti({
                    ...defaults,
                    particleCount,
                    origin: { x: randomInRange(0.1, 0.3), y: Math.random() - 0.2 }
                });
                confetti({
                    ...defaults,
                    particleCount,
                    origin: { x: randomInRange(0.7, 0.9), y: Math.random() - 0.2 }
                });
            }, 250);

            return () => clearInterval(interval);
        }
    }, [isOpen]);

    const handleGoToDashboard = () => {
        onClose();
        router.push('/');
    };

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <div className="mx-auto bg-green-100 dark:bg-green-900/30 p-3 rounded-full w-fit mb-4">
                        <PartyPopper className="h-8 w-8 text-green-600 dark:text-green-400" />
                    </div>
                    <DialogTitle className="text-center text-2xl">Demo Complete!</DialogTitle>
                    <DialogDescription className="text-center pt-2">
                        You've successfully explored the core capabilities of RegEngine.
                        From ingestion to regulatory intelligence, you're now ready to automate compliance.
                    </DialogDescription>
                </DialogHeader>

                <div className="flex flex-col gap-3 py-4">
                    <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg border">
                        <CheckCircle2 className="h-5 w-5 text-green-500" />
                        <span className="text-sm font-medium">FSMA 204 Traceability Rule Validated</span>
                    </div>
                    <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg border">
                        <CheckCircle2 className="h-5 w-5 text-green-500" />
                        <span className="text-sm font-medium">Compliance Gaps Identified</span>
                    </div>
                    <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg border">
                        <CheckCircle2 className="h-5 w-5 text-green-500" />
                        <span className="text-sm font-medium">Arbitrage Opportunities Calculated</span>
                    </div>
                </div>

                <DialogFooter className="flex-col sm:flex-col gap-2">
                    <Button size="lg" className="w-full" onClick={handleGoToDashboard}>
                        Go to Dashboard
                        <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                    <Button variant="outline" className="w-full" onClick={onRestart}>
                        <RotateCcw className="mr-2 h-4 w-4" />
                        Restart Demo Tour
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
