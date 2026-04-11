export type IndustrySegment = 'administration' | 'grocery' | 'produce' | 'seafood' | 'meat' | 'dairy' | 'organic' | 'specialty';

export interface Tenant {
    id: string;
    name: string;
    type?: string;
    industry?: IndustrySegment;
    subscriptionTier?: string;
}

export function getTenantById(id: string): Tenant | undefined {
    return MOCK_TENANTS.find(t => t.id === id);
}

export const MOCK_TENANTS: Tenant[] = [
    { id: '00000000-0000-0000-0000-000000000001', name: 'System Admin' },
    { id: 'e88a23d7-1f2e-46f5-9727-a931b5074bdc', name: "National Foods Corp" },
    { id: '40782263-0988-418b-b7eb-61a0121f6447', name: "MegaMart Inc" },
    { id: '1a61523d-9875-4896-ada6-747d4e58b5f5', name: "Premier Grocery Co" },
    { id: 'cf1637e1-feca-42da-b3b2-62a0fd87e9d3', name: "Fresh Market Group" },
    { id: '1801daa3-f52a-439c-a16f-08457f94679c', name: "ValueMart Corp" },
    { id: '0e0c2d58-d024-487a-ad2a-7ce44706d86d', name: "Demo Tenant" },
    { id: '66eaef68-0ed0-4872-9519-edce84cdce46', name: "Greenfield Greens" },
    { id: 'ff196233-03b0-4442-84fa-40313069caaf', name: "Sunrise Vegetables LLC" },
    { id: '6ceb6566-0204-4e56-a39a-e9c360f20087', name: "Hillside Organics" },
    { id: '85b4b4ed-4a6c-465c-868b-55de3ac25714', name: "Harvest Ready Foods" },
    { id: '6ca82fc5-7de0-4ee9-8566-9ccb574f034b', name: "Blue Ocean Seafood Co." },
    { id: 'c5ee3a69-0f1d-4031-bacf-94b4cca6ca4c', name: "Northern Waters Inc" },
    { id: 'ffe69d54-618a-4d14-900b-74ec03e0e787', name: "Pacific Catch LLC" },
    { id: '9a1170f0-08e0-4a9a-92a4-99a8159976ae', name: "Coastal Fisheries Group" },
    { id: '30c0dfcc-aa59-4849-a842-88742f7caf08', name: "Harbor Seafood Co." },
    { id: '3dcc4425-641c-442a-a027-61e814871bca', name: "Westcoast Catch" },
    { id: '4641c421-b5c3-4b30-ad72-76ef4ea0eff1', name: "Deepwater Foods" },
    { id: '0e3968ff-ed4d-4d4d-b0ad-1090666ccc2c', name: "Atlantic Harvest Inc" },
    { id: '8576b19e-9b88-47a0-902c-4aa0e5df994a', name: "Red Rock Fisheries" },
    { id: 'e818788b-79cc-4a45-b295-1afe0a7d5bae', name: "Sunrise Dairy LLC" },
    { id: '1e905c8c-9a8f-400a-b2c4-83212e2920c1', name: "Valley Green Farms" },
    { id: '29fcfa55-5ba8-4991-9629-07c1b349be45', name: "Riverbend Growers" },
    { id: '1edcb3ab-0334-497b-907a-3cd6d8409a8f', name: "Stonegate Farms" },
    { id: '7652823c-5562-4bbd-b2be-93fb1d48d71d', name: "Golden State Produce" },
    { id: '7a2e1f2c-8cf9-4d15-8aa1-699099a5137f', name: "Sunset Produce" },
];
