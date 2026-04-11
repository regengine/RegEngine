'use client';

import { useState } from 'react';
import { Play, Copy, Check, RotateCcw, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface CodePlaygroundProps {
    initialCode: string;
    title?: string;
    description?: string;
    language?: 'typescript' | 'javascript' | 'python';
    height?: string;
}

export function CodePlayground({
    initialCode,
    title = 'Interactive Playground',
    description,
    language = 'typescript',
    height = '400px',
}: CodePlaygroundProps) {
    const [code, setCode] = useState(initialCode);
    const [output, setOutput] = useState<string>('');
    const [isRunning, setIsRunning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);

    const handleRun = async () => {
        setIsRunning(true);
        setError(null);
        setOutput('');

        try {
            // Create a sandboxed console
            const logs: string[] = [];
            const mockConsole = {
                log: (...args: unknown[]) => {
                    logs.push(args.map(arg =>
                        typeof arg === 'object' ? JSON.stringify(arg, null, 2) : String(arg)
                    ).join(' '));
                },
                error: (...args: unknown[]) => {
                    logs.push('ERROR: ' + args.map(arg => String(arg)).join(' '));
                },
                warn: (...args: unknown[]) => {
                    logs.push('WARN: ' + args.map(arg => String(arg)).join(' '));
                },
            };

            // Execute code in isolated context
            const AsyncFunction = Object.getPrototypeOf(async function () { }).constructor;
            const executor = new AsyncFunction('console', code);

            await executor(mockConsole);

            setOutput(logs.join('\n') || '// Code executed successfully with no output');
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Unknown error occurred');
            setOutput('');
        } finally {
            setIsRunning(false);
        }
    };

    const handleCopy = async () => {
        await navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const handleReset = () => {
        setCode(initialCode);
        setOutput('');
        setError(null);
    };

    return (
        <Card className="overflow-hidden">
            <div className="bg-gradient-to-r from-slate-900 to-slate-800 p-4 border-b border-slate-700">
                <div className="flex items-center justify-between mb-2">
                    <div>
                        <h3 className="text-white font-semibold text-lg">{title}</h3>
                        {description && (
                            <p className="text-slate-400 text-sm mt-1">{description}</p>
                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        <Badge variant="secondary" className="text-xs">
                            {language}
                        </Badge>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={handleReset}
                            className="text-slate-400 hover:text-white"
                        >
                            <RotateCcw className="h-4 w-4" />
                        </Button>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={handleCopy}
                            className="text-slate-400 hover:text-white"
                        >
                            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                        </Button>
                        <Button
                            size="sm"
                            onClick={handleRun}
                            disabled={isRunning}
                            className="bg-re-brand hover:bg-re-brand-dark text-white"
                        >
                            <Play className="h-4 w-4 mr-2" />
                            {isRunning ? 'Running...' : 'Run Code'}
                        </Button>
                    </div>
                </div>
            </div>

            <div className="grid md:grid-cols-2 divide-x divide-slate-200 dark:divide-slate-700">
                {/* Code Editor */}
                <div className="relative" style={{ height }}>
                    <div className="absolute inset-0 overflow-auto">
                        <textarea
                            value={code}
                            onChange={(e) => setCode(e.target.value)}
                            className="w-full h-full p-4 font-mono text-sm bg-slate-950 text-slate-100 resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-inset"
                            style={{
                                tabSize: 2,
                                lineHeight: '1.5',
                            }}
                            spellCheck={false}
                        />
                    </div>
                </div>

                {/* Output Panel */}
                <div className="relative bg-slate-50 dark:bg-slate-900" style={{ height }}>
                    <div className="sticky top-0 bg-slate-100 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-4 py-2">
                        <span className="text-sm font-semibold text-slate-600 dark:text-slate-400">
                            Output
                        </span>
                    </div>
                    <div className="p-4 overflow-auto" style={{ height: `calc(${height} - 40px)` }}>
                        {error ? (
                            <div className="flex items-start gap-2 text-re-danger dark:text-re-danger">
                                <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
                                <pre className="font-mono text-sm whitespace-pre-wrap">{error}</pre>
                            </div>
                        ) : output ? (
                            <pre className="font-mono text-sm text-slate-800 dark:text-slate-200 whitespace-pre-wrap">
                                {output}
                            </pre>
                        ) : (
                            <p className="text-slate-400 italic text-sm">
                                Click "Run Code" to see output here
                            </p>
                        )}
                    </div>
                </div>
            </div>
        </Card>
    );
}
