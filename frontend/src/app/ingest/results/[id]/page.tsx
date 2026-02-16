import AnalysisResultClient from './AnalysisResultClient';

// Required for static export
export const dynamic = 'force-static';
export const generateStaticParams = async () => {
    return [{ id: '_build' }];
};

export default function AnalysisResultPage() {
    return <AnalysisResultClient />;
}
