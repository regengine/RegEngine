import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import Link from 'next/link';
import { ExternalLink, Code2, BookOpen } from 'lucide-react';

export interface ApiEndpoint {
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
    path: string;
    description: string;
    category: string;
    requestExample?: string;
    responseExample?: string;
    requiresAuth: boolean;
}

export interface SdkExample {
    language: 'typescript' | 'python' | 'go';
    installCommand: string;
    quickstartCode: string;
    description: string;
}

interface ApiReferenceSectionProps {
    vertical: string;
    baseUrl: string;
    endpoints: ApiEndpoint[];
    sdkExamples: SdkExample[];
    colorScheme?: 'blue' | 'orange' | 'red' | 'emerald' | 'purple' | 'amber';
}

const methodColors = {
    GET: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    POST: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    PUT: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
    DELETE: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    PATCH: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
};

export function ApiReferenceSection({
    vertical,
    baseUrl,
    endpoints,
    sdkExamples,
    colorScheme = 'blue',
}: ApiReferenceSectionProps) {
    // Group endpoints by category
    const groupedEndpoints = endpoints.reduce((acc, endpoint) => {
        if (!acc[endpoint.category]) {
            acc[endpoint.category] = [];
        }
        acc[endpoint.category].push(endpoint);
        return acc;
    }, {} as Record<string, ApiEndpoint[]>);

    return (
        <div className="space-y-12">
            {/* API Overview */}
            <section>
                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                    {vertical} API Reference
                </h2>
                <p className="text-lg text-gray-700 dark:text-gray-300 mb-6">
                    Complete API documentation for the {vertical} vertical. All endpoints require authentication via API key.
                </p>

                <div className="grid md:grid-cols-3 gap-6">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Base URL</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <code className="text-sm bg-gray-100 dark:bg-gray-900 px-2 py-1 rounded">
                                {baseUrl}
                            </code>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Authentication</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <code className="text-sm bg-gray-100 dark:bg-gray-900 px-2 py-1 rounded">
                                X-RegEngine-API-Key
                            </code>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-sm">Response Format</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <code className="text-sm bg-gray-100 dark:bg-gray-900 px-2 py-1 rounded">
                                application/json
                            </code>
                        </CardContent>
                    </Card>
                </div>

                <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                    <p className="text-sm text-gray-700 dark:text-gray-300">
                        <strong>Get your API key:</strong>{' '}
                        <Link
                            href="/api-keys"
                            className="text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-1"
                        >
                            Visit API Keys page
                            <ExternalLink className="h-3 w-3" />
                        </Link>
                    </p>
                </div>
            </section>

            {/* SDK Installation */}
            <section>
                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-6">
                    SDK Installation
                </h2>

                <Tabs defaultValue="typescript" className="w-full">
                    <TabsList className="grid w-full md:w-auto grid-cols-3">
                        <TabsTrigger value="typescript">TypeScript</TabsTrigger>
                        <TabsTrigger value="python">Python</TabsTrigger>
                        <TabsTrigger value="go">Go</TabsTrigger>
                    </TabsList>

                    {sdkExamples.map((example) => (
                        <TabsContent key={example.language} value={example.language}>
                            <Card>
                                <CardHeader>
                                    <CardTitle>
                                        {example.language === 'typescript' && 'TypeScript/JavaScript'}
                                        {example.language === 'python' && 'Python'}
                                        {example.language === 'go' && 'Go'}
                                    </CardTitle>
                                    <CardDescription>{example.description}</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div>
                                        <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                                            Installation:
                                        </p>
                                        <div className="bg-gray-900 rounded-lg p-4">
                                            <code className="text-sm text-green-400 font-mono">
                                                {example.installCommand}
                                            </code>
                                        </div>
                                    </div>

                                    <div>
                                        <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                                            Quickstart:
                                        </p>
                                        <div className="bg-gray-900 rounded-lg p-4 overflow-x-auto">
                                            <pre className="text-sm text-green-400 font-mono">
                                                {example.quickstartCode}
                                            </pre>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </TabsContent>
                    ))}
                </Tabs>
            </section>

            {/* Endpoints */}
            <section>
                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-6">
                    API Endpoints
                </h2>

                <div className="space-y-8">
                    {Object.entries(groupedEndpoints).map(([category, categoryEndpoints]) => (
                        <div key={category}>
                            <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
                                {category}
                            </h3>
                            <div className="space-y-4">
                                {categoryEndpoints.map((endpoint, idx) => (
                                    <Card key={idx} className="border-gray-200 dark:border-gray-700">
                                        <CardHeader>
                                            <div className="flex items-start justify-between">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-3 mb-2">
                                                        <Badge className={methodColors[endpoint.method]}>
                                                            {endpoint.method}
                                                        </Badge>
                                                        <code className="text-sm font-mono text-gray-900 dark:text-gray-100">
                                                            {endpoint.path}
                                                        </code>
                                                    </div>
                                                    <CardDescription>{endpoint.description}</CardDescription>
                                                </div>
                                                {endpoint.requiresAuth && (
                                                    <Badge variant="outline" className="ml-2">
                                                        Auth Required
                                                    </Badge>
                                                )}
                                            </div>
                                        </CardHeader>

                                        {(endpoint.requestExample || endpoint.responseExample) && (
                                            <CardContent>
                                                <Tabs defaultValue="request" className="w-full">
                                                    <TabsList>
                                                        {endpoint.requestExample && (
                                                            <TabsTrigger value="request">Request</TabsTrigger>
                                                        )}
                                                        {endpoint.responseExample && (
                                                            <TabsTrigger value="response">Response</TabsTrigger>
                                                        )}
                                                    </TabsList>

                                                    {endpoint.requestExample && (
                                                        <TabsContent value="request">
                                                            <div className="bg-gray-900 rounded-lg p-4 overflow-x-auto">
                                                                <pre className="text-sm text-green-400 font-mono">
                                                                    {endpoint.requestExample}
                                                                </pre>
                                                            </div>
                                                        </TabsContent>
                                                    )}

                                                    {endpoint.responseExample && (
                                                        <TabsContent value="response">
                                                            <div className="bg-gray-900 rounded-lg p-4 overflow-x-auto">
                                                                <pre className="text-sm text-green-400 font-mono">
                                                                    {endpoint.responseExample}
                                                                </pre>
                                                            </div>
                                                        </TabsContent>
                                                    )}
                                                </Tabs>
                                            </CardContent>
                                        )}
                                    </Card>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* Additional Resources */}
            <section>
                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-6">
                    Additional Resources
                </h2>
                <div className="grid md:grid-cols-2 gap-6">
                    <Link href={`/docs/${vertical.toLowerCase()}`}>
                        <Card className="hover:shadow-lg transition-shadow cursor-pointer h-full">
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <BookOpen className="h-6 w-6 text-blue-600 dark:text-blue-400" />
                                    <CardTitle>Full Documentation</CardTitle>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-gray-600 dark:text-gray-400">
                                    Complete guides, tutorials, and best practices for the {vertical} API.
                                </p>
                            </CardContent>
                        </Card>
                    </Link>

                    <Link href="/playground">
                        <Card className="hover:shadow-lg transition-shadow cursor-pointer h-full">
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <Code2 className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
                                    <CardTitle>Interactive Playground</CardTitle>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-gray-600 dark:text-gray-400">
                                    Test API calls in your browser. See real responses instantly.
                                </p>
                            </CardContent>
                        </Card>
                    </Link>
                </div>
            </section>
        </div>
    );
}
