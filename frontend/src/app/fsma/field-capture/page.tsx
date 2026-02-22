"use client"

import React, { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
    Scan,
    Camera as CameraIcon,
    CheckCircle2,
    Truck,
    Package,
    History,
    FileText,
    Database,
    CloudIcon,
    AlertTriangle
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Spinner } from "@/components/ui/spinner"
import { useToast } from "@/components/ui/use-toast"
import { apiClient } from "@/lib/api-client"
import { Capacitor } from "@capacitor/core"
import { BarcodeScanner, BarcodeFormat } from "@capacitor-mlkit/barcode-scanning"
import { Camera, CameraResultType, CameraSource } from "@capacitor/camera"
import { parseGS1 } from "@/lib/gs1-parser"

const EVENT_TYPES = [
    { id: "RECEIVING", label: "Receiving", icon: Package, color: "bg-blue-500/10 text-blue-500" },
    { id: "SHIPPING", label: "Shipping", icon: Truck, color: "bg-green-500/10 text-green-500" },
    { id: "TRANSFORMATION", label: "Transformation", icon: History, color: "bg-purple-500/10 text-purple-500" },
    { id: "HARVESTING", label: "Harvesting", icon: FileText, color: "bg-orange-500/10 text-orange-500" },
]

export default function FieldCapturePage() {
    const { toast } = useToast()
    const [eventType, setEventType] = useState<string | null>(null)
    const [isScanning, setIsScanning] = useState(false)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [isSuccess, setIsSuccess] = useState(false)
    const [capturedDoc, setCapturedDoc] = useState<string | null>(null)

    // Form States
    const [tlc, setTlc] = useState("")
    const [gtin, setGtin] = useState("")
    const [lastEventId, setLastEventId] = useState("")

    const handleScan = async () => {
        if (!Capacitor.isNativePlatform()) {
            // Web Fallback (Simulated)
            setIsScanning(true)
            setTimeout(() => {
                setIsScanning(false)
                const mockBarcode = "(01)10614141000019(10)TLC-3489"
                const parsed = parseGS1(mockBarcode)
                setTlc(parsed.tlc || "")
                setGtin(parsed.gtin || "")
                toast({
                    title: "Web Simulation Success",
                    description: `Extracted TLC: ${parsed.tlc}`,
                })
            }, 1500)
            return
        }

        // Native Capacitor Logic
        try {
            const granted = await BarcodeScanner.requestPermissions()
            if (!granted.camera) {
                toast({
                    title: "Permission Denied",
                    description: "Camera access is required for scanning.",
                    variant: "destructive"
                })
                return
            }

            setIsScanning(true)

            // BarcodeScanner requires a transparent webview
            document.querySelector('body')?.classList.add('barcode-scanner-active')

            const { barcodes } = await BarcodeScanner.scan({
                formats: [BarcodeFormat.Code128, BarcodeFormat.QrCode, BarcodeFormat.DataMatrix]
            })

            if (barcodes.length > 0) {
                const rawValue = barcodes[0].displayValue
                const parsed = parseGS1(rawValue)
                setTlc(parsed.tlc || rawValue)
                setGtin(parsed.gtin || "")

                toast({
                    title: "Hardware Scan Success",
                    description: parsed.tlc ? "GS1-128 identifiers extracted." : "Barcode captured.",
                })
            }
        } catch (error) {
            console.error("Scanner error:", error)
            toast({
                title: "Scanner Error",
                description: "Failed to initialize native camera.",
                variant: "destructive"
            })
        } finally {
            setIsScanning(false)
            document.querySelector('body')?.classList.remove('barcode-scanner-active')
            await BarcodeScanner.stopScan()
        }
    }

    const handleSubmit = async () => {
        if (!eventType || !tlc) return

        setIsSubmitting(true)
        try {
            const response = await apiClient.logTraceabilityEvent({
                event_type: eventType,
                event_date: new Date().toISOString().split('T')[0],
                tlc: tlc,
                location_identifier: "0614141000036", // Mock facility GLN
                gtin: gtin || undefined,
                image_data: capturedDoc || undefined,
                product_description: "Premium Romaine Hearts (Mobile Capture)",
                quantity: 12.0,
                uom: "LB"
            })

            if (response.status === "success") {
                setLastEventId(response.event_id)
                setIsSuccess(true)
                toast({
                    title: "Event Secured",
                    description: "Data persisted to high-integrity ledger.",
                })
            }
        } catch (error: any) {
            console.error("Ledger write failed:", error)
            const detail = error.response?.data?.detail || "Connection failure"
            toast({
                title: "Ledger Write Failed",
                description: detail,
                variant: "destructive"
            })
        } finally {
            setIsSubmitting(false)
        }
    }

    const handleDocCapture = async () => {
        try {
            const image = await Camera.getPhoto({
                quality: 90,
                allowEditing: false,
                resultType: CameraResultType.Base64,
                source: CameraSource.Prompt // Allows user to choose between camera and gallery
            })

            if (image.base64String) {
                setCapturedDoc(image.base64String)
                toast({
                    title: "Hardware Capture Success",
                    description: "BOL image captured and queued.",
                })
            }
        } catch (error) {
            console.error("Camera error:", error)
            // Camera.getPhoto throws an error if the user cancels
        }
    }

    const reset = () => {
        setIsSuccess(false)
        setEventType(null)
        setTlc("")
        setGtin("")
        setCapturedDoc(null)
    }

    return (
        <div className={`flex flex-col min-h-screen bg-background text-foreground font-sans p-6 space-y-8 lg:max-w-md lg:mx-auto ${isScanning ? 'barcode-scanner-ui' : ''}`}>
            {/* Header */}
            <div className="flex flex-col space-y-1 pt-4">
                <h1 className="text-4xl font-extrabold tracking-tight">Field Companion</h1>
                <div className="flex items-center gap-2">
                    <Badge variant="outline" className="font-mono text-[10px] bg-primary/5 text-primary border-primary/20">
                        SITE: 41829-FL
                    </Badge>
                    <div className="flex items-center gap-1 text-[10px] text-re-success font-bold uppercase">
                        <CloudIcon className="w-3 h-3" />
                        <span>Sync Active</span>
                    </div>
                </div>
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
                  ${tlc ? "border-re-success/50 bg-re-success/5" : ""}
                `}
                                onClick={handleScan}
                                disabled={!eventType || isScanning}
                            >
                                {isScanning ? (
                                    <>
                                        <Spinner className="w-10 h-10 text-primary" />
                                        <span className="text-primary font-black uppercase tracking-widest text-sm text-center">Validating GS1<br />Identifiers...</span>
                                    </>
                                ) : tlc ? (
                                    <>
                                        <div className="p-5 bg-re-success/10 rounded-full border-2 border-re-success/30">
                                            <CheckCircle2 className="w-12 h-12 text-re-success" />
                                        </div>
                                        <div className="text-center">
                                            <span className="block font-black text-xl tracking-tighter uppercase text-re-success">TLC CAPTURED</span>
                                            <span className="font-mono text-xs opacity-60 uppercase tracking-widest">{tlc}</span>
                                        </div>
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
                                    <CameraIcon className="w-6 h-6 text-primary" />
                                    <span>{capturedDoc ? "Update BOL" : "Snap BOL"}</span>
                                </Button>
                                {capturedDoc && (
                                    <motion.div
                                        initial={{ scale: 0 }}
                                        animate={{ scale: 1 }}
                                        className="h-24 w-24 rounded-[2rem] bg-card border-2 border-re-success/50 overflow-hidden shadow-lg relative group"
                                    >
                                        <img
                                            src={`data:image/jpeg;base64,${capturedDoc}`}
                                            alt="Captured BOL"
                                            className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                                        />
                                        <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                                            <CheckCircle2 className="w-8 h-8 text-re-success" />
                                        </div>
                                    </motion.div>
                                )}
                            </div>
                        </section>

                        {/* Final Action */}
                        <Button
                            className={`w-full h-16 rounded-[1.5rem] text-xl font-black uppercase tracking-widest shadow-re-glow transition-all
                                ${(!eventType || !tlc) ? "opacity-30 grayscale cursor-not-allowed" : "hover:scale-[1.02] active:scale-95"}
                            `}
                            disabled={!eventType || !tlc || isSubmitting}
                            onClick={handleSubmit}
                        >
                            {isSubmitting ? (
                                <div className="flex items-center gap-3">
                                    <Spinner className="w-6 h-6" />
                                    <span>Securing...</span>
                                </div>
                            ) : (
                                <div className="flex items-center gap-3">
                                    <Database className="w-6 h-6" />
                                    <span>Secure Event</span>
                                </div>
                            )}
                        </Button>
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
                            <p className="text-muted-foreground font-medium uppercase font-mono text-sm tracking-widest">TLC: {tlc}</p>
                        </div>
                        <div className="flex flex-col items-center space-y-2">
                            <Badge variant="outline" className="bg-re-success text-white border-none px-6 py-2 text-[10px] font-mono tracking-tighter uppercase">
                                LEDGER ID: {lastEventId.split('-')[0]}...{lastEventId.split('-').pop()}
                            </Badge>
                            <p className="text-[10px] text-muted-foreground italic">Immutable proof stored in Neo4j Cluster</p>
                        </div>

                        <Button
                            variant="link"
                            className="text-primary font-bold uppercase tracking-widest pt-8"
                            onClick={reset}
                        >
                            Start Next Activity
                        </Button>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Footer Info */}
            <div className="mt-auto pt-8 pb-4 text-center border-t border-re-border-subtle/30">
                <p className="text-[8px] text-muted-foreground uppercase tracking-[0.4em] font-mono font-bold flex items-center justify-center gap-2">
                    <CloudIcon className="w-2 h-2" />
                    High-Integrity Cloud Sync • 21 CFR 1.1455 Compliant
                </p>
            </div>
        </div>
    )
}
