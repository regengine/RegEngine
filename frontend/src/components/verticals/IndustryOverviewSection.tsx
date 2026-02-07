import { LucideIcon } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

export interface RegulationInfo {
    name: string;
    shortName: string;
    description: string;
    authority: string;
}

export interface Challenge {
    title: string;
    description: string;
    impact: 'high' | 'medium' | 'low';
}

export interface MarketplaceSolution {
    category: string;
    examples: string[];
    pros: string[];
    cons: string[];
    typicalCost: string;
}

export interface ApproachComparison {
    better: string[];
    tradeoffs: string[];
    notFor: string[];
}

interface IndustryOverviewSectionProps {
    industry: string;
    industryDescription: string;
    regulations: RegulationInfo[];
    challenges: Challenge[];
    marketplaceSolutions: MarketplaceSolution[];
    ourApproach: ApproachComparison;
    icon?: LucideIcon;
}

export function IndustryOverviewSection({
    industry,
    industryDescription,
    regulations,
    challenges,
    marketplaceSolutions,
    ourApproach,
    icon: Icon,
}: IndustryOverviewSectionProps) {
    return (
        <div className="space-y-12">
            {/* Industry Overview */}
            <section>
                <div className="flex items-center gap-3 mb-4">
                    {Icon && <Icon className="h-8 w-8 text-gray-700 dark:text-gray-300" />}
                    <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                        The {industry} Industry
                    </h2>
                </div>
                <p className="text-lg text-gray-700 dark:text-gray-300 leading-relaxed">
                    {industryDescription}
                </p>
            </section>

            {/* Regulatory Framework */}
            <section>
                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-6">
                    Regulatory Framework
                </h2>
                <div className="grid md:grid-cols-2 gap-6">
                    {regulations.map((reg) => (
                        <Card key={reg.shortName} className="border-gray-200 dark:border-gray-700">
                            <CardHeader>
                                <div className="flex items-start justify-between">
                                    <div>
                                        <CardTitle className="text-lg">{reg.name}</CardTitle>
                                        <Badge variant="outline" className="mt-2">
                                            {reg.shortName}
                                        </Badge>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                                    {reg.description}
                                </p>
                                <p className="text-xs text-gray-500 dark:text-gray-500">
                                    <strong>Authority:</strong> {reg.authority}
                                </p>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </section>

            {/* Compliance Challenges */}
            <section>
                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-6">
                    Compliance Challenges
                </h2>
                <div className="space-y-4">
                    {challenges.map((challenge, idx) => (
                        <Card
                            key={idx}
                            className={`border-l-4 ${challenge.impact === 'high'
                                    ? 'border-l-red-500 bg-red-50 dark:bg-red-950/20'
                                    : challenge.impact === 'medium'
                                        ? 'border-l-amber-500 bg-amber-50 dark:bg-amber-950/20'
                                        : 'border-l-blue-500 bg-blue-50 dark:bg-blue-950/20'
                                }`}
                        >
                            <CardContent className="pt-6">
                                <div className="flex items-start justify-between mb-2">
                                    <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                                        {challenge.title}
                                    </h3>
                                    <Badge
                                        variant={
                                            challenge.impact === 'high'
                                                ? 'destructive'
                                                : challenge.impact === 'medium'
                                                    ? 'default'
                                                    : 'secondary'
                                        }
                                        className="ml-2"
                                    >
                                        {challenge.impact.toUpperCase()}
                                    </Badge>
                                </div>
                                <p className="text-sm text-gray-700 dark:text-gray-300">
                                    {challenge.description}
                                </p>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </section>

            {/* Marketplace Solutions */}
            <section>
                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-6">
                    Current Marketplace Solutions
                </h2>
                <div className="space-y-6">
                    {marketplaceSolutions.map((solution, idx) => (
                        <Card key={idx} className="border-gray-200 dark:border-gray-700">
                            <CardHeader>
                                <CardTitle className="flex items-center justify-between">
                                    <span>{solution.category}</span>
                                    <Badge variant="outline">{solution.typicalCost}</Badge>
                                </CardTitle>
                                <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
                                    Examples: {solution.examples.join(', ')}
                                </p>
                            </CardHeader>
                            <CardContent>
                                <div className="grid md:grid-cols-2 gap-6">
                                    <div>
                                        <h4 className="font-semibold text-emerald-700 dark:text-emerald-400 mb-2">
                                            ✅ Pros
                                        </h4>
                                        <ul className="space-y-1 text-sm text-gray-700 dark:text-gray-300">
                                            {solution.pros.map((pro, i) => (
                                                <li key={i}>&bull; {pro}</li>
                                            ))}
                                        </ul>
                                    </div>
                                    <div>
                                        <h4 className="font-semibold text-red-700 dark:text-red-400 mb-2">
                                            ❌ Cons
                                        </h4>
                                        <ul className="space-y-1 text-sm text-gray-700 dark:text-gray-300">
                                            {solution.cons.map((con, i) => (
                                                <li key={i}>&bull; {con}</li>
                                            ))}
                                        </ul>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </section>

            {/* RegEngine's Approach */}
            <section>
                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-6">
                    RegEngine's Approach
                </h2>
                <div className="grid md:grid-cols-3 gap-6">
                    {/* Better */}
                    <Card className="border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/20">
                        <CardHeader>
                            <CardTitle className="text-emerald-700 dark:text-emerald-400">
                                ✅ Where We're Better
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ul className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
                                {ourApproach.better.map((item, i) => (
                                    <li key={i} className="flex items-start gap-2">
                                        <span className="text-emerald-600 dark:text-emerald-400 mt-0.5">
                                            •
                                        </span>
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </CardContent>
                    </Card>

                    {/* Trade-offs */}
                    <Card className="border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/20">
                        <CardHeader>
                            <CardTitle className="text-amber-700 dark:text-amber-400">
                                ⚠️ Trade-offs to Consider
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ul className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
                                {ourApproach.tradeoffs.map((item, i) => (
                                    <li key={i} className="flex items-start gap-2">
                                        <span className="text-amber-600 dark:text-amber-400 mt-0.5">
                                            •
                                        </span>
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </CardContent>
                    </Card>

                    {/* Not For */}
                    <Card className="border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/20">
                        <CardHeader>
                            <CardTitle className="text-red-700 dark:text-red-400">
                                ❌ Not Ideal For
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ul className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
                                {ourApproach.notFor.map((item, i) => (
                                    <li key={i} className="flex items-start gap-2">
                                        <span className="text-red-600 dark:text-red-400 mt-0.5">
                                            •
                                        </span>
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </CardContent>
                    </Card>
                </div>
            </section>
        </div>
    );
}
