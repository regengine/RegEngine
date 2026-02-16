import React from 'react';

// Required for static export
export const dynamic = 'force-static';
export const generateStaticParams = async () => {
    return [
        { vertical: 'food-safety' },
        { vertical: 'energy' },
        { vertical: 'healthcare' }
    ];
};

export default function WhitepaperListPage() {
    return <div>Whitepaper List placeholder</div>;
}
