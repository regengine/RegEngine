'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Loader2, Lock, LayoutDashboard } from 'lucide-react';
import Link from 'next/link';

export default function LoginPage() {
    // Force HMR update
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();
    const { login } = useAuth();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        try {
            const response = await apiClient.login(email, password);

            // Update auth context
            login(
                response.access_token,
                response.user,
                response.tenant_id
            );

            // Redirect based on role
            if (response.user.is_sysadmin) {
                router.push('/sysadmin');
            } else {
                router.push('/dashboard');
            }
        } catch (err: unknown) {
            console.error('Login error:', err);
            // Handle axios-style errors with response property
            const apiError = err as { response?: { status?: number } };
            if (apiError.response?.status === 401) {
                setError('Invalid email or password');
            } else if (apiError.response?.status === 403) {
                setError('Account access disabled');
            } else {
                setError('An unexpected error occurred. Please try again.');
            }
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center p-4">
            <Card className="w-full max-w-md shadow-lg border-t-4 border-t-primary">
                <CardHeader className="space-y-1">
                    <div className="flex justify-center mb-4">
                        <div className="p-3 bg-primary/10 rounded-full">
                            <Lock className="w-8 h-8 text-primary" />
                        </div>
                    </div>
                    <CardTitle className="text-2xl font-bold text-center">Welcome back</CardTitle>
                    <CardDescription className="text-center">
                        Sign in to your RegEngine account
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        {error && (
                            <div
                                id="login-error"
                                role="alert"
                                aria-live="polite"
                                className="p-3 text-sm text-red-500 bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800 rounded-md animate-in fade-in slide-in-from-top-2"
                            >
                                {error}
                            </div>
                        )}
                        <div className="space-y-2">
                            <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70" htmlFor="email">
                                Email
                            </label>
                            <Input
                                id="email"
                                type="email"
                                placeholder="name@example.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                disabled={isLoading}
                                required
                                autoComplete="email"
                                aria-invalid={!!error}
                                aria-describedby={error ? "login-error" : undefined}
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70" htmlFor="password">
                                Password
                            </label>
                            <Input
                                id="password"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                disabled={isLoading}
                                required
                                autoComplete="current-password"
                                aria-invalid={!!error}
                                aria-describedby={error ? "login-error" : undefined}
                            />
                        </div>
                        <Button className="w-full" type="submit" disabled={isLoading}>
                            {isLoading ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Signing in...
                                </>
                            ) : (
                                'Sign In'
                            )}
                        </Button>
                        <div className="text-center text-sm text-muted-foreground pt-2">
                            <Link href="/" className="hover:text-primary transition-colors flex items-center justify-center gap-2">
                                <LayoutDashboard className="w-4 h-4" />
                                Return to public site
                            </Link>
                        </div>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
