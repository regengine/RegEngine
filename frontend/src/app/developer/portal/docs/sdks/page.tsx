'use client';

import { useState } from 'react';
import { CodeBlock } from '@/components/developer/CodeBlock';
import { Badge } from '@/components/ui/badge';
import {
  Package,
  ExternalLink,
  Download,
  Copy,
  Check,
} from 'lucide-react';

interface SDKInfo {
  name: string;
  language: string;
  installCommand: string;
  packageManager: string;
  version: string;
  pythonVersion?: string;
  description: string;
  gitHubUrl: string;
  helloWorld: string;
  icon: React.ReactNode;
}

export default function SDKsPage() {
  const [copiedCommand, setCopiedCommand] = useState<string | null>(null);

  const sdks: SDKInfo[] = [
    {
      name: 'Python',
      language: 'python',
      installCommand: 'pip install regengine',
      packageManager: 'pip',
      version: '1.0.0',
      pythonVersion: '3.8+',
      description: 'Full-featured Python SDK with async support and type hints',
      gitHubUrl: 'https://github.com/regengine/regengine-python',
      helloWorld: `from regengine import RegEngine

client = RegEngine(api_key='sk_...')

# Ingest a CTE
response = await client.events.ingest(
    cte_id='cte_123',
    data={'content': 'Supply chain record'}
)

print(response.status)`,
      icon: <Package className="w-6 h-6" />,
    },
    {
      name: 'Node.js',
      language: 'javascript',
      installCommand: 'npm install @regengine/sdk',
      packageManager: 'npm',
      version: '1.0.0',
      description: 'TypeScript support, ESM and CommonJS compatible',
      gitHubUrl: 'https://github.com/regengine/regengine-js',
      helloWorld: `import { RegEngine } from '@regengine/sdk';

const client = new RegEngine({
  apiKey: 'sk_...'
});

// Ingest a CTE
const response = await client.events.ingest({
  cteId: 'cte_123',
  data: { content: 'Supply chain record' }
});

console.log(response.status);`,
      icon: <Package className="w-6 h-6" />,
    },
    {
      name: 'Go',
      language: 'go',
      installCommand: 'go get github.com/regengine/regengine-go',
      packageManager: 'go',
      version: '1.0.0',
      pythonVersion: '1.21+',
      description: 'Context support, concurrency-safe, minimal dependencies',
      gitHubUrl: 'https://github.com/regengine/regengine-go',
      helloWorld: `package main

import (
  "context"
  "log"
  "github.com/regengine/regengine-go"
)

func main() {
  client := regengine.NewClient("sk_...")
  
  resp, err := client.Events.Ingest(context.Background(), &regengine.IngestRequest{
    CTEID: "cte_123",
    Data:  map[string]interface{}{"content": "Supply chain record"},
  })
  
  if err != nil {
    log.Fatal(err)
  }
  
  log.Println(resp.Status)
}`,
      icon: <Package className="w-6 h-6" />,
    },
  ];

  const communityLibraries = [
    { name: 'Ruby', status: 'Coming soon' },
    { name: 'PHP', status: 'Coming soon' },
    { name: 'Java', status: 'Coming soon' },
  ];

  const handleCopy = (command: string, id: string) => {
    navigator.clipboard.writeText(command);
    setCopiedCommand(id);
    setTimeout(() => setCopiedCommand(null), 2000);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-4">
            <Package className="w-8 h-8" style={{ color: 'var(--re-brand)' }} />
            <h1
              className="text-4xl font-bold"
              style={{ color: 'var(--re-text-primary)' }}
            >
              SDKs & Libraries
            </h1>
          </div>
          <p
            style={{ color: 'var(--re-text-muted)' }}
            className="text-lg"
          >
            Official SDKs for Node.js, Python, and Go. Community libraries for additional languages.
          </p>
        </div>

        {/* SDK Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
          {sdks.map((sdk) => (
            <div
              key={sdk.name}
              className="p-6 rounded-lg border border-slate-700"
              style={{ backgroundColor: 'rgba(30, 41, 59, 0.5)' }}
            >
              {/* Icon and Language */}
              <div className="flex items-center justify-between mb-4">
                <div
                  className="w-10 h-10 rounded-lg flex items-center justify-center"
                  style={{ backgroundColor: 'rgba(var(--re-brand-rgb), 0.1)' }}
                >
                  {sdk.icon}
                </div>
                <Badge variant="outline">{sdk.version}</Badge>
              </div>

              {/* Language Title and Description */}
              <h3
                className="text-xl font-semibold mb-2"
                style={{ color: 'var(--re-text-primary)' }}
              >
                {sdk.name}
              </h3>
              <p
                className="text-sm mb-4"
                style={{ color: 'var(--re-text-muted)' }}
              >
                {sdk.description}
                {sdk.pythonVersion && ` (${sdk.pythonVersion})`}
              </p>

              {/* Install Command */}
              <div
                className="p-3 rounded-lg mb-4 font-mono text-sm flex items-center justify-between"
                style={{ backgroundColor: 'rgba(0, 0, 0, 0.3)' }}
              >
                <code style={{ color: 'var(--re-text-primary)' }}>
                  {sdk.installCommand}
                </code>
                <button
                  onClick={() => handleCopy(sdk.installCommand, sdk.name)}
                  className="ml-2 p-1 hover:opacity-75 transition-opacity"
                  style={{ color: 'var(--re-brand)' }}
                  title="Copy to clipboard"
                >
                  {copiedCommand === sdk.name ? (
                    <Check className="w-4 h-4" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                </button>
              </div>

              {/* Hello World Code */}
              <div className="mb-4">
                <p
                  className="text-xs font-semibold mb-2 uppercase tracking-wider"
                  style={{ color: 'var(--re-text-muted)' }}
                >
                  Quick Start
                </p>
                <CodeBlock
                  code={sdk.helloWorld}
                  language={sdk.language}
                />
              </div>

              {/* GitHub Link */}
              <a
                href={sdk.gitHubUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-sm font-medium hover:opacity-75 transition-opacity"
                style={{ color: 'var(--re-brand)' }}
              >
                View on GitHub
                <ExternalLink className="w-4 h-4" />
              </a>
            </div>
          ))}
        </div>

        {/* Community Libraries Section */}
        <section className="mb-12">
          <h2
            className="text-2xl font-bold mb-6"
            style={{ color: 'var(--re-text-primary)' }}
          >
            Community Libraries
          </h2>
          <div
            className="p-6 rounded-lg border border-slate-700"
            style={{ backgroundColor: 'rgba(30, 41, 59, 0.5)' }}
          >
            <p
              className="mb-4"
              style={{ color: 'var(--re-text-muted)' }}
            >
              Community-maintained SDKs for additional languages are in development:
            </p>
            <div className="space-y-3">
              {communityLibraries.map((lib) => (
                <div
                  key={lib.name}
                  className="flex items-center justify-between p-3 rounded-lg"
                  style={{ backgroundColor: 'rgba(0, 0, 0, 0.2)' }}
                >
                  <span style={{ color: 'var(--re-text-primary)' }}>
                    {lib.name}
                  </span>
                  <Badge variant="secondary">{lib.status}</Badge>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* OpenAPI Spec Section */}
        <section>
          <h2
            className="text-2xl font-bold mb-6"
            style={{ color: 'var(--re-text-primary)' }}
          >
            OpenAPI Specification
          </h2>
          <div
            className="p-6 rounded-lg border border-slate-700"
            style={{ backgroundColor: 'rgba(30, 41, 59, 0.5)' }}
          >
            <p
              className="mb-4"
              style={{ color: 'var(--re-text-muted)' }}
            >
              Download the complete OpenAPI 3.0 specification for the RegEngine API. Use it to generate SDKs in other languages or integrate with tools like Postman.
            </p>
            <a
              href="/openapi.json"
              download
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-opacity hover:opacity-75"
              style={{
                backgroundColor: 'var(--re-brand)',
                color: 'white',
              }}
            >
              <Download className="w-4 h-4" />
              Download OpenAPI Spec
            </a>
          </div>
        </section>
      </div>
    </div>
  );
}