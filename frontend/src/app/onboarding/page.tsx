import { redirect } from 'next/navigation';

type OnboardingRedirectPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function toQueryString(searchParams?: Record<string, string | string[] | undefined>): string {
  if (!searchParams) return '';

  const query = new URLSearchParams();

  for (const [key, value] of Object.entries(searchParams)) {
    if (Array.isArray(value)) {
      for (const entry of value) {
        query.append(key, entry);
      }
      continue;
    }

    if (typeof value === 'string') {
      query.append(key, value);
    }
  }

  const queryString = query.toString();
  return queryString ? `?${queryString}` : '';
}

export default async function OnboardingRedirectPage({ searchParams }: OnboardingRedirectPageProps) {
  const resolvedSearchParams = searchParams ? await searchParams : undefined;
  redirect(`/onboarding/supplier-flow${toQueryString(resolvedSearchParams)}`);
}
