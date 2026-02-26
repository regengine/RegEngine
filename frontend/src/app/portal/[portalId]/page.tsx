// Required for Next.js static export (output: 'export') compatibility
// Portal pages are dynamic — no static pre-rendering needed
export function generateStaticParams() {
    return [];
}

import SupplierPortalPage from './SupplierPortalPage';

export default function Page() {
    return <SupplierPortalPage />;
}
