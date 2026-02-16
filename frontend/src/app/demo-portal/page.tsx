import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function DemoPortalPage() {
    return (
        <div className="container mx-auto py-12 px-4">
            <div className="max-w-4xl mx-auto space-y-8">
                <div className="text-center space-y-4">
                    <Badge variant="outline" className="text-emerald-500 border-emerald-500/20 bg-emerald-500/10">
                        Phase 7: Global Scaling
                    </Badge>
                    <h1 className="text-5xl font-extrabold tracking-tight text-white sm:text-6xl">
                        Fractal Swarm <span className="text-emerald-500">Demo Portal</span>
                    </h1>
                    <p className="text-xl text-slate-400">
                        Experience the power of autonomous regulatory remediation. Launch a one-click vertical audit.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <Card className="bg-[#0f172a] border-slate-800 hover:border-emerald-500/50 transition-all duration-300">
                        <CardHeader>
                            <CardTitle className="text-white">HIPAA Fortress Audit</CardTitle>
                            <CardDescription>Automated PHI access audit & decryption validation.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Button className="w-full bg-emerald-600 hover:bg-emerald-500">Launch Audit</Button>
                        </CardContent>
                    </Card>

                    <Card className="bg-[#0f172a] border-slate-800 hover:border-blue-500/50 transition-all duration-300">
                        <CardHeader>
                            <CardTitle className="text-white">AS9100D Traceability Check</CardTitle>
                            <CardDescription>Aerospace component traceability & 8130-3 verification.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Button className="w-full bg-blue-600 hover:bg-blue-500">Launch Audit</Button>
                        </CardContent>
                    </Card>
                </div>

                <Card className="bg-slate-900/50 border-emerald-500/20">
                    <CardHeader>
                        <CardTitle className="text-white flex items-center gap-2">
                            <span className="text-emerald-500">🛒</span> Compliance Risk Marketplace
                        </CardTitle>
                        <CardDescription>Trade anonymized risk benchmarks across the swarm.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            {[
                                { vertical: "Health", benchmark: "92% HIPAA Latency Compliance", trend: "+2.1%" },
                                { vertical: "Pharma", benchmark: "84% ALCOA+ Data Integrity", trend: "-1.4%" },
                                { vertical: "Energy", benchmark: "98% CIP-013 SBOM Validation", trend: "+0.5%" },
                            ].map((item) => (
                                <div key={item.vertical} className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg">
                                    <div>
                                        <span className="text-white font-medium">{item.vertical}</span>
                                        <p className="text-xs text-slate-400">{item.benchmark}</p>
                                    </div>
                                    <Badge className={item.trend.startsWith('+') ? "bg-emerald-500/20 text-emerald-500" : "bg-red-500/20 text-red-500"}>
                                        {item.trend}
                                    </Badge>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>

                <div className="bg-slate-900/50 rounded-xl p-8 border border-slate-800">
                    <h3 className="text-lg font-semibold text-white mb-4">Swarm Intelligence Feed</h3>
                    <div className="space-y-3 font-mono text-sm text-slate-400">
                        <div className="flex items-center gap-2">
                            <span className="text-emerald-500">[SYSTEM]</span> Swarm v7.0.1 active.
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-blue-500">[RELAY]</span> Redpanda handoff detected: Bot-Legal {"->"} Bot-Finance.
                        </div>
                        <div className="flex items-center gap-2 text-slate-500">
                            [TUNER] Predicting 90-day risk for Health vertical...
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
