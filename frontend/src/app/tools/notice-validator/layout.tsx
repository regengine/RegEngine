import type { Metadata } from 'next';

export const metadata: Metadata = {
    title: 'FSMA Request Validator | FDA Response Checker | RegEngine',
    description: 'Check whether an FDA request response includes the core FSMA 204 record elements. Heuristic checker for draft responses.',
    openGraph: {
        title: 'FSMA Request Validator — RegEngine',
        description: 'Check whether an FDA request response includes the core FSMA 204 record elements.',
        type: 'website',
        url: 'https://www.regengine.co/tools/notice-validator',
    },
};

export default function NoticeValidatorLayout({ children }: { children: React.ReactNode }) {
    return children;
}
