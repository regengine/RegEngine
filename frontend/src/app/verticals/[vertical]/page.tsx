import { NextRequest, NextResponse } from 'next/server';

// Required for static export
export const dynamic = 'force-static';
export const generateStaticParams = async () => {
    return [{ vertical: 'food-safety' }, { vertical: 'energy' }, { vertical: 'healthcare' }];
};

export default async function VerticalPage() {
    return null;
}
