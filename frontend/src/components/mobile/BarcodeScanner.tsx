'use client';

import { useEffect, useRef, useState } from 'react';
import { Html5Qrcode, Html5QrcodeSupportedFormats } from 'html5-qrcode';
import { Button } from '@/components/ui/button';
import { AlertCircle, Camera, RefreshCw } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

interface BarcodeScannerProps {
    onScan: (decodedText: string) => void;
    onError?: (error: string) => void;
}

export function BarcodeScanner({ onScan, onError }: BarcodeScannerProps) {
    const [isScanning, setIsScanning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const scannerRef = useRef<Html5Qrcode | null>(null);
    const scannerRegionId = 'html5qr-code-full-region';

    useEffect(() => {
        return () => {
            // Cleanup on unmount
            if (scannerRef.current && isScanning) {
                scannerRef.current.stop().catch(console.error);
            }
        };
    }, [isScanning]);

    const startScanning = async () => {
        setError(null);
        try {
            const devices = await Html5Qrcode.getCameras();
            if (!devices || devices.length === 0) {
                throw new Error('No cameras found.');
            }

            // Prefer back camera
            const backCamera = devices.find(device =>
                device.label.toLowerCase().includes('back') ||
                device.label.toLowerCase().includes('environment')
            );
            const cameraId = backCamera ? backCamera.id : devices[0].id;

            if (!scannerRef.current) {
                scannerRef.current = new Html5Qrcode(scannerRegionId, {
                    formatsToSupport: [
                        Html5QrcodeSupportedFormats.QR_CODE,
                        Html5QrcodeSupportedFormats.CODE_128,
                        Html5QrcodeSupportedFormats.DATA_MATRIX,
                        Html5QrcodeSupportedFormats.EAN_13,
                        Html5QrcodeSupportedFormats.UPC_A
                    ],
                    verbose: false
                });
            }

            await scannerRef.current.start(
                cameraId,
                {
                    fps: 10,
                    qrbox: { width: 250, height: 250 },
                    aspectRatio: 1.0
                },
                (decodedText) => {
                    // Success callback
                    // Haptic feedback
                    if (navigator.vibrate) navigator.vibrate(200);

                    setIsScanning(false);
                    if (scannerRef.current) {
                        scannerRef.current.stop().catch(console.error);
                    }
                    onScan(decodedText);
                },
                (errorMessage) => {
                    // Error callback (called frequently when no code found)
                    // Don't log to console to avoid noise
                }
            );

            setIsScanning(true);
        } catch (err) {
            console.error('Failed to start scanner:', err);
            const message = err instanceof Error ? err.message : 'Failed to start camera';
            setError(message);
            if (onError) onError(message);
        }
    };

    const stopScanning = async () => {
        if (scannerRef.current && isScanning) {
            try {
                await scannerRef.current.stop();
                setIsScanning(false);
            } catch (err) {
                console.error('Failed to stop scanner:', err);
            }
        }
    };

    return (
        <div className="w-full flex flex-col items-center gap-4">
            <div
                id={scannerRegionId}
                className="w-full max-w-sm aspect-square bg-black rounded-lg overflow-hidden relative"
            >
                {!isScanning && !error && (
                    <div className="absolute inset-0 flex items-center justify-center text-white/50">
                        <Camera className="h-12 w-12" />
                    </div>
                )}
            </div>

            {error && (
                <Alert variant="destructive" className="max-w-sm">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Scanner Error</AlertTitle>
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            )}

            <div className="flex gap-2">
                {!isScanning ? (
                    <Button onClick={startScanning} size="lg" className="w-full">
                        <Camera className="mr-2 h-4 w-4" />
                        Scan Barcode
                    </Button>
                ) : (
                    <Button onClick={stopScanning} variant="destructive" size="lg" className="w-full">
                        Stop Scanning
                    </Button>
                )}
            </div>

            <p className="text-xs text-muted-foreground text-center max-w-xs">
                Supports QR (GS1 Digital Link), GS1-128, DataMatrix, EAN-13, and UPC-A.
                Ensure good lighting and hold steady.
            </p>
        </div>
    );
}
