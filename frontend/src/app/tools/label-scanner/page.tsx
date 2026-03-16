'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Camera, Upload, X } from 'lucide-react';
import html2canvas from 'html2canvas';
import { AlertCircle, CheckCircle2, Loader } from 'lucide-react';

interface ScanResult {
  success: boolean;
  text?: string;
  error?: string;
  confidence?: number;
}

export default function LabelScanner() {
  const [image, setImage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Initialize camera
  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' }
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        setCameraActive(true);
      }
    } catch (err) {
      console.error('Camera error:', err);
      alert('Unable to access camera');
    }
  };
  // Stop camera
  const stopCamera = () => {
    if (videoRef.current && videoRef.current.srcObject) {
      const tracks = (videoRef.current.srcObject as MediaStream).getTracks();
      tracks.forEach(track => track.stop());
      setCameraActive(false);
    }
  };

  // Capture photo from camera
  const capturePhoto = () => {
    if (videoRef.current && canvasRef.current) {
      const context = canvasRef.current.getContext('2d');
      if (context) {
        canvasRef.current.width = videoRef.current.videoWidth;
        canvasRef.current.height = videoRef.current.videoHeight;
        context.drawImage(videoRef.current, 0, 0);
        const imageData = canvasRef.current.toDataURL('image/jpeg');
        setImage(imageData);
        stopCamera();
      }
    }
  };

  // Handle file upload
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        setImage(event.target?.result as string);
      };
      reader.readAsDataURL(file);
    }
  };
  // Scan the label
  const scanLabel = async () => {
    if (!image) return;
    
    setLoading(true);
    setResult(null);
    
    try {
      const response = await fetch('/api/tools/label-scanner', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image })
      });

      const data: ScanResult = await response.json();
      setResult(data);
    } catch (err) {
      console.error('Scan error:', err);
      setResult({
        success: false,
        error: 'Failed to scan label. Please try again.'
      });
    } finally {
      setLoading(false);
    }
  };

  // Clear image and results
  const clearImage = () => {
    setImage(null);
    setResult(null);
  };
  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-4">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">Label Scanner</h1>
          <p className="text-gray-600">Scan product labels to extract regulatory information</p>
        </div>

        {/* Main Content */}
        <div className="bg-white rounded-lg shadow-lg p-8 space-y-6">
          
          {/* Camera or Image Display */}
          {!image ? (
            <div className="space-y-4">
              {!cameraActive ? (
                <div className="space-y-3">
                  <button
                    onClick={startCamera}
                    className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-6 rounded-lg flex items-center justify-center gap-2 transition"
                  >
                    <Camera size={20} />
                    Start Camera
                  </button>
                  <label className="w-full bg-gray-100 hover:bg-gray-200 text-gray-800 font-semibold py-3 px-6 rounded-lg flex items-center justify-center gap-2 cursor-pointer transition">
                    <Upload size={20} />
                    Upload Image
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                  </label>
                </div>
              ) : (
                <div className="space-y-3">
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    className="w-full rounded-lg bg-black"
                  />
                  <div className="flex gap-3">
                    <button
                      onClick={capturePhoto}
                      className="flex-1 bg-green-600 hover:bg-green-700 text-white font-semibold py-3 px-6 rounded-lg transition"
                    >
                      Capture Photo
                    </button>
                    <button
                      onClick={stopCamera}
                      className="flex-1 bg-red-600 hover:bg-red-700 text-white font-semibold py-3 px-6 rounded-lg transition"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="relative">
                <img
                  src={image}
                  alt="Captured label"
                  className="w-full rounded-lg"
                />
                <button
                  onClick={clearImage}
                  className="absolute top-2 right-2 bg-red-600 hover:bg-red-700 text-white p-2 rounded-full transition"
                >
                  <X size={20} />
                </button>
              </div>
              <button
                onClick={scanLabel}
                disabled={loading}
                className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-400 text-white font-semibold py-3 px-6 rounded-lg flex items-center justify-center gap-2 transition"
              >
                {loading ? (
                  <>
                    <Loader size={20} className="animate-spin" />
                    Scanning...
                  </>
                ) : (
                  <>
                    <Camera size={20} />
                    Scan Label
                  </>
                )}
              </button>
            </div>
          )}

          {/* Results Display */}
          {result && (
            <div className={`rounded-lg p-4 ${result.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
              <div className="flex items-start gap-3">
                {result.success ? (
                  <CheckCircle2 size={24} className="text-green-600 flex-shrink-0 mt-1" />
                ) : (
                  <AlertCircle size={24} className="text-red-600 flex-shrink-0 mt-1" />
                )}
                <div className="flex-1">
                  {result.success ? (
                    <>
                      <h3 className="font-semibold text-green-900 mb-2">Scan Successful</h3>
                      <div className="bg-white rounded p-3 mb-2">
                        <p className="text-gray-700 text-sm whitespace-pre-wrap">{result.text}</p>
                      </div>                      {result.confidence && (
                        <p className="text-sm text-green-700">
                          Confidence: {(result.confidence * 100).toFixed(1)}%
                        </p>
                      )}
                    </>
                  ) : (
                    <>
                      <h3 className="font-semibold text-red-900 mb-1">Scan Failed</h3>
                      <p className="text-red-700 text-sm">{result.error}</p>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Info Section */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h3 className="font-semibold text-blue-900 mb-2">How it works:</h3>
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• Capture or upload a clear photo of the product label</li>
              <li>• Click "Scan Label" to extract text and regulatory info</li>
              <li>• Results include ingredient lists, warnings, and compliance data</li>
              <li>• Use for quick regulatory compliance checks</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Hidden Canvas for Photo Capture */}
      <canvas ref={canvasRef} className="hidden" />
    </div>
  );
}