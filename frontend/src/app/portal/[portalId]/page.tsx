export const dynamic = "force-static";

// Static export in CI requires at least one concrete dynamic path.
export function generateStaticParams() {
    return [{ portalId: "preview" }];
}

import SupplierPortalPage from './SupplierPortalPage';

export default function Page() {
    return <SupplierPortalPage />;
}
