"use client"

import React, { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
    Scan,
    Camera,
    CheckCircle2,
    Truck,
    Package,
    History,
    FileText
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Spinner } from "@/components/ui/spinner"

const EVENT_TYPES = [
    { id: "receiving", label: "Receiving", icon: Package, color: "bg-blue-500/10 text-blue-500" },
    { id: "shipping", label: "Shipping", icon: Truck, color: "bg-green-500/10 text-green-500" },
    { id: "transformation", label: "Transformation", icon: History, color: "bg-purple-500/10 text-purple-500" },
    { id: "harvesting", label: "Harvesting", icon: FileText, color: "bg-orange-500/10 text-orange-500" },
]

export default function FieldCapturePage() {
    const [eventType, setEventType] = useState<string | null>(null)
    const [isScanning, setIsScanning] = useState(false)
    const [isSuccess, setIsSuccess] = useState(false)
    const [capturedDoc, setCapturedDoc] = useState<string | null>(null)

    const handleScan = () => {
        setIsScanning(true)
        setTimeout(() => {
            setIsScanning(false)
            setIsSuccess(true)
            setTimeout(() => setIsSuccess(false), 3000)
        }, 2000)
    }

    const handleDocCapture = () => {
        setCapturedDoc("manifest_capture_001.jpg")
    }

    return (
        <div className="flex flex-col min-h-screen bg-background text-foreground font-sans p-6 space-y-8 lg:max-w-md lg:mx-auto">
            {/* Header */}
            <div className="flex flex-col space-y-1 pt-4">
                <h1 className="text-4xl font-extrabold tracking-tight">Field Companion</h1>
                <p className="text-muted-foreground font-mono text-xs uppercase tracking-[0.2em] opacity-80">
                    FSMA 204 | Site ID: 41829-FL
                </p>
            </div>

            <AnimatePresence mode="wait">
                {!isSuccess ? (
                    <motion.div
                        key="capture-form"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        className="flex-1 flex flex-col space-y-8"
                    >
                        {/* Step 1: Event Type */}
                        <section className="space-y-4">
                            <label className="text-[10px] font-bold uppercase tracking-[0.3em] text-muted-foreground ml-1">
                                Step 1: Activity Type
                            </label>
                            <div className="grid grid-cols-2 gap-4">
                                {EVENT_TYPES.map((type) => {
                                    const Icon = type.icon
                                    const isActive = eventType === type.id
                                    return (
                                        <button
                                            key={type.id}
                                            onClick={() => setEventType(type.id)}
                                            className={`
                        flex flex-col items-center justify-center p-8 rounded-[2rem] border-2 transition-all duration-300
                        ${isActive
                                                    ? "border-primary bg-primary/10 shadow-re-glow scale-[0.96]"
                                                    : "border-re-border-subtle bg-card hover:border-re-border-strong"}
                      `}
                                        >
                                            <div className={`p-4 rounded-full mb-3 shadow-inner ${type.color}`}>
                                                <Icon className="w-8 h-8" />
                                            </div>
                                            <span className="font-bold text-base tracking-tight">{type.label}</span>
                                        </button>
                                    )
                                })}
                            </div>
                        </section>

                        {/* Step 2: Barcode Scan */}
                        <section className="space-y-4">
                            <label className="text-[10px] font-bold uppercase tracking-[0.3em] text-muted-foreground ml-1">
                                Step 2: Traceability Scan
                            </label>
                            <Button
                                variant="outline"
                                className={`
                  w-full h-40 flex flex-col items-center justify-center space-y-4 border-dashed border-[3px] rounded-[2.5rem] transition-all
                  ${isScanning ? "animate-pulse" : "hover:border-primary hover:bg-primary/5 active:scale-95"}
                  ${!eventType ? "opacity-40" : "opacity-100"}
                `}
                                onClick={handleScan}
                                disabled={!eventType || isScanning}
                            >
                                {isScanning ? (
                                    <>
                                        <Spinner className="w-10 h-10 text-primary" />
                                        <span className="text-primary font-black uppercase tracking-widest text-sm">Validating GS1...</span>
                                    </>
                                ) : (
                                    <>
                                        <div className="p-5 bg-background rounded-full border-2">
                                            <Scan className="w-12 h-12 text-primary" />
                                        </div>
                                        <span className="font-black text-xl tracking-tighter uppercase">Activate Scanner</span>
                                    </>
                                )}
                            </Button>
                        </section>

                        {/* Step 3: Document Backup */}
                        <section className="space-y-4">
                            <label className="text-[10px] font-bold uppercase tracking-[0.3em] text-muted-foreground ml-1">
                                Step 3: Manifest Capture
                            </label>
                            <div className="flex gap-4">
                                <Button
                                    variant="outline"
                                    className="flex-1 h-24 rounded-[2rem] space-x-3 text-lg font-bold border-2 active:scale-95"
                                    onClick={handleDocCapture}
                                    disabled={!eventType}
                                >
                                    <Camera className="w-6 h-6 text-primary" />
                                    <span>{capturedDoc ? "Update BOL" : "Snap BOL"}</span>
                                </Button>
                                {capturedDoc && (
                                    <motion.div
                                        initial={{ scale: 0 }}
                                        animate={{ scale: 1 }}
                                        className="h-24 w-24 rounded-[2rem] bg-re-success/10 border-2 border-re-success/30 flex items-center justify-center shadow-lg"
                                    >
                                        <FileText className="w-8 h-8 text-re-success" />
                                    </motion.div>
                                )}
                            </div>
                        </section>
                    </motion.div>
                ) : (
                    <motion.div
                        key="success-state"
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="flex-1 flex flex-col items-center justify-center space-y-8"
                    >
                        <motion.div
                            animate={{
                                scale: [1, 1.2, 1],
                                rotate: [0, 10, 0]
                            }}
                            transition={{ duration: 0.5 }}
                            className="w-32 h-32 rounded-full bg-re-success/20 flex items-center justify-center border-4 border-re-success/40 shadow-re-glow"
                        >
                            <CheckCircle2 className="w-20 h-20 text-re-success" />
                        </motion.div>
                        <div className="text-center space-y-3">
                            <h2 className="text-4xl font-black tracking-tighter uppercase">Event Secured</h2>
                            <p className="text-muted-foreground font-medium">Traceability Lot: 41829-FL-2202</p>
                        </div>
                        <Badge variant="outline" className="bg-re-success text-white border-none px-6 py-2 text-sm font-mono tracking-widest uppercase">
                            LEDGER PK: 0x82f...a12c
                        </Badge>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Footer Info */}
            <div className="mt-auto pt-8 pb-4 text-center border-t border-re-border-subtle/30">
                <p className="text-[8px] text-muted-foreground uppercase tracking-[0.4em] font-mono font-bold">
                    High-Integrity Cloud Sync • 21 CFR 1.1455 Compliant
                </p>
            </div>
        </div>
    )
}
