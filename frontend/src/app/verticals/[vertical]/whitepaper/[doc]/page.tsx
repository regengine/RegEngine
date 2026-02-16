import React from 'react';

// Required for static export
export const dynamic = 'force-static';
export const generateStaticParams = async () => {
    return [
        { vertical: 'food-safety', doc: 'fsma-204' },
        { vertical: 'energy', doc: 'cip-013' }
    ];
};

export default function WhitepaperDocPage() {
    return <div>Whitepaper Doc placeholder</div>;
}
