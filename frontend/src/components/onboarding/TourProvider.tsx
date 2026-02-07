'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { driver, Driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import { usePathname } from 'next/navigation';
import { useDemoProgress } from './DemoProgress';
import { LEGAL_DEMO_SCRIPT } from './legal-demo-script';

interface TourContextType {
    startTour: () => void;
    hasSeenTour: boolean;
    dismissTour: () => void;
}

const TourContext = createContext<TourContextType | undefined>(undefined);

export function TourProvider({ children }: { children: React.ReactNode }) {
    const [hasSeenTour, setHasSeenTour] = useState(false);
    const [tourDismissed, setTourDismissed] = useState(false);
    const [driverObj, setDriverObj] = useState<Driver | null>(null);
    const pathname = usePathname();
    const { isActive: isDemoActive } = useDemoProgress();

    useEffect(() => {
        const seen = localStorage.getItem('regengine_tour_seen');
        const dismissed = localStorage.getItem('regengine_tour_dismissed');
        if (seen) {
            setHasSeenTour(true);
        }
        if (dismissed) {
            setTourDismissed(true);
        }
    }, []);

    // Effect to trigger tour steps when page changes during active demo
    useEffect(() => {
        // Don't show tour if it was dismissed or already seen
        if (isDemoActive && !tourDismissed && pathname && LEGAL_DEMO_SCRIPT[pathname]) {
            // Small delay to ensure DOM is ready
            const timer = setTimeout(() => {
                const steps = LEGAL_DEMO_SCRIPT[pathname];

                const driverInstance = driver({
                    showProgress: true,
                    animate: true,
                    steps: steps,
                    doneBtnText: 'Next',
                    nextBtnText: 'Next',
                    prevBtnText: 'Back',
                    onDestroyed: () => {
                        // Mark tour as dismissed when user closes it
                        setTourDismissed(true);
                        localStorage.setItem('regengine_tour_dismissed', 'true');
                    },
                });

                driverInstance.drive();
                setDriverObj(driverInstance);
            }, 800);

            return () => clearTimeout(timer);
        }
    }, [isDemoActive, pathname, tourDismissed]);

    const startTour = () => {
        // Reset dismissed state and restart tour
        setTourDismissed(false);
        localStorage.removeItem('regengine_tour_dismissed');
        if (driverObj) {
            driverObj.drive();
        }
    };

    const dismissTour = () => {
        setTourDismissed(true);
        localStorage.setItem('regengine_tour_dismissed', 'true');
        if (driverObj) {
            driverObj.destroy();
        }
    };

    return (
        <TourContext.Provider value={{ startTour, hasSeenTour, dismissTour }}>
            {children}
        </TourContext.Provider>
    );
}

export function useTour() {
    const context = useContext(TourContext);
    if (context === undefined) {
        throw new Error('useTour must be used within a TourProvider');
    }
    return context;
}
