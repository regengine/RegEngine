'use client';

import { useRef, useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Camera, RefreshCw, Check, X } from 'lucide-react';

interface ImageCaptureProps {
    onCapture: (imageData: string) => void;
}

export function ImageCapture({ onCapture }: ImageCaptureProps) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [stream, setStream] = useState<MediaStream | null>(null);
    const [capturedImage, setCapturedImage] = useState<string | null>(null);
    const [isCameraActive, setIsCameraActive] = useState(false);

    const startCamera = async () => {
        try {
            const mediaStream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'environment' } // Prefer back camera
            });
            setStream(mediaStream);
            if (videoRef.current) {
                videoRef.current.srcObject = mediaStream;
            }
            setIsCameraActive(true);
        } catch (err) {
            console.error('Error accessing camera:', err);
        }
    };

    const stopCamera = useCallback(() => {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            setStream(null);
            setIsCameraActive(false);
        }
    }, [stream]);

    const capturePhoto = () => {
        if (videoRef.current && canvasRef.current) {
            const video = videoRef.current;
            const canvas = canvasRef.current;

            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;

            const context = canvas.getContext('2d');
            if (context) {
                context.drawImage(video, 0, 0, canvas.width, canvas.height);
                // Compress to JPEG 0.8 quality
                const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
                setCapturedImage(dataUrl);
                stopCamera();
            }
        }
    };

    const retake = () => {
        setCapturedImage(null);
        startCamera();
    };

    const confirm = () => {
        if (capturedImage) {
            onCapture(capturedImage);
        }
    };

    return (
        <div className="w-full flex flex-col items-center gap-4">
            <div className="w-full max-w-sm aspect-[3/4] bg-black rounded-lg overflow-hidden relative">
                {/* Camera Preview */}
                {!capturedImage && (
                    <video
                        ref={videoRef}
                        autoPlay
                        playsInline
                        muted
                        className={`w-full h-full object-cover ${!isCameraActive ? 'hidden' : ''}`}
                    />
                )}

                {/* Captured Image Preview */}
                {capturedImage && (
                    <img
                        src={capturedImage}
                        alt="Captured"
                        className="w-full h-full object-cover"
                    />
                )}

                {/* Placeholder / Start Button Overlay */}
                {!isCameraActive && !capturedImage && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-muted/10">
                        <Camera className="h-16 w-16 text-muted-foreground/50" />
                        <Button onClick={startCamera}>Start Camera</Button>
                    </div>
                )}

                <canvas ref={canvasRef} className="hidden" />
            </div>

            <div className="flex gap-4 w-full max-w-sm justify-center">
                {isCameraActive && !capturedImage && (
                    <Button
                        onClick={capturePhoto}
                        size="lg"
                        className="rounded-full h-16 w-16 p-0 border-4 border-white/20"
                        variant="default"
                    >
                        <div className="h-12 w-12 bg-white rounded-full" />
                        <span className="sr-only">Capture</span>
                    </Button>
                )}

                {capturedImage && (
                    <div className="flex gap-4 w-full">
                        <Button
                            onClick={confirm}
                            className="flex-1 bg-green-600 hover:bg-green-700"
                        >
                            <Check className="mr-2 h-4 w-4" />
                            Use Photo
                        </Button>
                        <Button
                            onClick={retake}
                            variant="outline"
                            className="flex-1"
                        >
                            <RefreshCw className="mr-2 h-4 w-4" />
                            Retake
                        </Button>
                    </div>
                )}
            </div>
        </div>
    );
}
