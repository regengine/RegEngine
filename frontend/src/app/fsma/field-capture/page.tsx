'use client';

import React, { useState, useEffect } from 'react';
import {
    Camera,
    Truck,
    ThermometerSnowflake,
    Package,
    ArrowRightLeft,
    CheckCircle2,
    ChevronLeft,
    ScanLine,
    MapPin,
    Clock,
    Plus,
    Minus
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import Link from 'next/link';

type CTEType = 'Harvesting' | 'Cooling' | 'Receiving' | 'Transformation' | 'Shipping' | null;

export default function FieldCapturePage() {
    const [step, setStep] = useState<number>(1);
    const [activity, setActivity] = useState<CTEType>(null);
    const [lotCode, setLotCode] = useState<string>('');
    const [quantity, setQuantity] = useState<number>(100);
    const [isScanning, setIsScanning] = useState<boolean>(false);

    // Auto-filled context
    const [currentTime, setCurrentTime] = useState<string>('');
    const [currentDate, setCurrentDate] = useState<string>('');

    useEffect(() => {
        const now = new Date();
        setCurrentTime(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        setCurrentDate(now.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' }));
    }, []);

    const activities: { id: CTEType; icon: React.ReactNode; color: string; bgColor: string }[] = [
        { id: 'Receiving', icon: <Package size={32} />, color: 'text-emerald-500', bgColor: 'bg-emerald-500/10' },
        { id: 'Shipping', icon: <Truck size={32} />, color: 'text-sky-500', bgColor: 'bg-sky-500/10' },
        { id: 'Cooling', icon: <ThermometerSnowflake size={32} />, color: 'text-indigo-500', bgColor: 'bg-indigo-500/10' },
        { id: 'Harvesting', icon: <ScanLine size={32} />, color: 'text-amber-500', bgColor: 'bg-amber-500/10' },
        { id: 'Transformation', icon: <ArrowRightLeft size={32} />, color: 'text-purple-500', bgColor: 'bg-purple-500/10' },
    ];

    const handleSimulateScan = () => {
        setIsScanning(true);
        setTimeout(() => {
            setLotCode('TLC-998-002A-FX');
            setIsScanning(false);
            setStep(3);
        }, 1500);
    };

    const nextStep = () => setStep(s => s + 1);
    const prevStep = () => setStep(s => s - 1);

    const resetForm = () => {
        setActivity(null);
        setLotCode('');
        setQuantity(100);
        setStep(1);
    };

    return (
        <div className="min-h-[100dvh] bg-slate-950 text-slate-50 font-sans selection:bg-emerald-500/30 flex flex-col">

            {/* Minimal App Header */}
            <header className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-900/50 backdrop-blur-md sticky top-0 z-10">
                <div className="flex items-center gap-3">
                    {step > 1 && step < 4 && (
                        <button onClick={prevStep} className="p-2 -ml-2 rounded-full hover:bg-slate-800 transition-colors">
                            <ChevronLeft size={24} />
                        </button>
                    )}
                    <div className="flex flex-col">
                        <span className="text-sm font-bold tracking-wider text-emerald-400">REGENGINE</span>
                        <span className="text-[10px] text-slate-400 font-medium uppercase tracking-widest">Field Capture</span>
                    </div>
                </div>

                {/* Auto-filled context */}
                <div className="flex items-center gap-4 text-xs font-mono text-slate-400">
                    <div className="flex items-center gap-1.5 bg-slate-800/50 px-2 py-1 rounded border border-slate-700/50">
                        <MapPin size={12} className="text-emerald-500" />
                        <span>Dock 4 (GLN...01)</span>
                    </div>
                </div>
            </header>

            <main className="flex-1 flex flex-col p-4 md:p-6 max-w-lg mx-auto w-full">
                <AnimatePresence mode="wait">

                    {/* STEP 1: SELECT ACTIVITY */}
                    {step === 1 && (
                        <motion.div
                            key="step1"
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 20 }}
                            className="flex flex-col flex-1"
                        >
                            <h1 className="text-3xl font-extrabold mb-2 text-white">What are you logging?</h1>
                            <p className="text-slate-400 mb-8">Tap an activity to begin capture.</p>

                            <div className="grid grid-cols-2 gap-4">
                                {activities.map((act) => (
                                    <button
                                        key={act.id}
                                        onClick={() => { setActivity(act.id); nextStep(); }}
                                        className={`flex flex-col items-center justify-center p-6 rounded-3xl border-2 transition-all active:scale-95
                                            ${activity === act.id
                                                ? 'border-emerald-500 bg-emerald-500/10 shadow-[0_0_30px_rgba(16,185,129,0.15)]'
                                                : 'border-slate-800 bg-slate-900 hover:border-slate-700 hover:bg-slate-800/50'
                                            }
                                        `}
                                    >
                                        <div className={`w-16 h-16 rounded-2xl ${act.bgColor} ${act.color} flex items-center justify-center mb-4`}>
                                            {act.icon}
                                        </div>
                                        <span className={`font-bold text-lg ${activity === act.id ? 'text-white' : 'text-slate-300'}`}>
                                            {act.id}
                                        </span>
                                    </button>
                                ))}
                            </div>
                        </motion.div>
                    )}

                    {/* STEP 2: SCAN OR LOT CODE */}
                    {step === 2 && (
                        <motion.div
                            key="step2"
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 20 }}
                            className="flex flex-col flex-1"
                        >
                            <div className="flex items-center gap-3 mb-6 bg-slate-900 p-3 rounded-2xl border border-slate-800">
                                <div className="p-2 rounded-xl bg-slate-800 text-emerald-400">
                                    {activities.find(a => a.id === activity)?.icon}
                                </div>
                                <div>
                                    <div className="text-xs text-slate-400 uppercase tracking-widest font-bold">Current Task</div>
                                    <div className="text-xl font-bold text-white">{activity} Event</div>
                                </div>
                            </div>

                            <h1 className="text-3xl font-extrabold mb-8 text-white">Scan the Product</h1>

                            {/* Camera Viewfinder Mock */}
                            <div className="relative aspect-square w-full rounded-3xl overflow-hidden bg-black border-2 border-slate-800 shadow-2xl mb-6 flex flex-col items-center justify-center group cursor-pointer" onClick={handleSimulateScan}>
                                {/* Grid background to simulate camera noise/texture */}
                                <div className="absolute inset-0 opacity-20" style={{ backgroundImage: 'radial-gradient(var(--re-text-muted) 1px, transparent 1px)', backgroundSize: '16px 16px' }}></div>

                                {/* Target brackets */}
                                <div className="absolute inset-8 border-[3px] border-emerald-500/50 rounded-xl"></div>
                                <div className="absolute inset-[30px] border-[3px] border-emerald-500 rounded-xl border-dashed opacity-0 group-hover:opacity-100 transition-opacity"></div>

                                {/* Scanning Laser */}
                                <div className={`absolute left-8 right-8 h-0.5 bg-emerald-400 shadow-[0_0_15px_rgba(52,211,153,0.8)] z-10 ${isScanning ? 'animate-[scan_1.5s_ease-in-out_infinite]' : 'top-1/2 -mt-px opacity-50'}`}></div>

                                <div className="relative z-20 flex flex-col items-center">
                                    <Camera size={48} className={`mb-4 ${isScanning ? 'text-emerald-400' : 'text-slate-500'}`} />
                                    <span className={`text-xl font-bold ${isScanning ? 'text-emerald-400' : 'text-slate-400'}`}>
                                        {isScanning ? 'Reading GS1-128...' : 'Tap to Scan Barcode'}
                                    </span>
                                </div>
                            </div>

                            <div className="flex items-center gap-4 my-4">
                                <div className="flex-1 h-px bg-slate-800"></div>
                                <span className="text-slate-500 font-bold tracking-widest text-sm uppercase">OR</span>
                                <div className="flex-1 h-px bg-slate-800"></div>
                            </div>

                            <button
                                onClick={() => { setLotCode('MANUAL-ENTRY-77'); nextStep(); }}
                                className="w-full py-5 rounded-2xl border-2 border-slate-800 bg-slate-900 text-slate-300 font-bold text-lg hover:bg-slate-800 transition-colors active:scale-95"
                            >
                                Type Lot Number Used
                            </button>
                        </motion.div>
                    )}

                    {/* STEP 3: QUANTITY & CONFIRM */}
                    {step === 3 && (
                        <motion.div
                            key="step3"
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 20 }}
                            className="flex flex-col flex-1"
                        >
                            <h1 className="text-3xl font-extrabold mb-8 text-white">Confirm Details</h1>

                            <div className="space-y-4 mb-auto">
                                {/* Immutable Data (Auto-filled) */}
                                <div className="bg-slate-900 p-5 rounded-3xl border border-slate-800 space-y-4">
                                    <div className="flex justify-between items-center pb-4 border-b border-slate-800/50">
                                        <span className="text-slate-400 font-medium">Activity</span>
                                        <span className="text-white font-bold text-lg flex items-center gap-2">
                                            {activity} <CheckCircle2 size={16} className="text-emerald-500" />
                                        </span>
                                    </div>
                                    <div className="flex justify-between items-center pb-4 border-b border-slate-800/50">
                                        <span className="text-slate-400 font-medium">Lot Code</span>
                                        <span className="text-emerald-400 font-mono font-bold text-lg bg-emerald-500/10 px-3 py-1 rounded-lg">
                                            {lotCode}
                                        </span>
                                    </div>
                                    <div className="flex justify-between items-center">
                                        <span className="text-slate-400 font-medium">Timestamp</span>
                                        <span className="text-slate-300 font-mono text-sm flex items-center gap-2">
                                            <Clock size={14} /> {currentDate} {currentTime}
                                        </span>
                                    </div>
                                </div>

                                {/* Mutable Data (Quantity) */}
                                <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800 mt-6">
                                    <label className="block text-center text-slate-400 font-bold uppercase tracking-widest text-xs mb-4">
                                        Total Cases
                                    </label>
                                    <div className="flex items-center justify-between bg-black/50 p-2 rounded-2xl border border-slate-800">
                                        <button
                                            onClick={() => setQuantity(Math.max(1, quantity - 10))}
                                            className="w-16 h-16 flex items-center justify-center bg-slate-800 hover:bg-slate-700 rounded-xl text-slate-300 active:scale-95 transition-all"
                                        >
                                            <Minus size={32} />
                                        </button>
                                        <div className="font-mono text-5xl font-bold text-white tracking-tighter">
                                            {quantity}
                                        </div>
                                        <button
                                            onClick={() => setQuantity(quantity + 10)}
                                            className="w-16 h-16 flex items-center justify-center bg-slate-800 hover:bg-slate-700 rounded-xl text-slate-300 active:scale-95 transition-all"
                                        >
                                            <Plus size={32} />
                                        </button>
                                    </div>
                                </div>
                            </div>

                            <button
                                onClick={nextStep}
                                className="mt-8 w-full py-6 rounded-3xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-black text-xl shadow-[0_10px_40px_rgba(16,185,129,0.3)] active:scale-95 transition-all flex justify-center items-center gap-3"
                            >
                                Log to Immutable Ledger <CheckCircle2 size={24} />
                            </button>
                        </motion.div>
                    )}

                    {/* STEP 4: SUCCESS */}
                    {step === 4 && (
                        <motion.div
                            key="step4"
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="flex flex-col flex-1 items-center justify-center text-center"
                        >
                            <motion.div
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                transition={{ type: "spring", bounce: 0.5, delay: 0.2 }}
                                className="w-32 h-32 bg-emerald-500 rounded-full flex items-center justify-center mb-8 shadow-[0_0_100px_rgba(16,185,129,0.4)]"
                            >
                                <CheckCircle2 size={64} className="text-slate-950" />
                            </motion.div>

                            <h1 className="text-4xl font-black text-white mb-4 tracking-tight">Event Secured</h1>
                            <p className="text-emerald-400 text-lg font-mono mb-2">{lotCode}</p>
                            <p className="text-slate-400 mb-12">Cryptographically hashed and synced to the primary node.</p>

                            <button
                                onClick={resetForm}
                                className="w-full py-5 rounded-2xl border-2 border-slate-700 bg-slate-800 text-white font-bold text-lg hover:bg-slate-700 active:scale-95 transition-all"
                            >
                                Log Another Event
                            </button>

                            <Link href="/fsma/dashboard" className="mt-6 text-slate-500 hover:text-slate-300 font-medium underline underline-offset-4">
                                Return to FSMA Dashboard
                            </Link>

                        </motion.div>
                    )}

                </AnimatePresence>
            </main>

            <style jsx global>{`
                @keyframes scan {
                    0% { top: 10%; }
                    50% { top: 90%; }
                    100% { top: 10%; }
                }
            `}</style>
        </div>
    );
}
