import type { MetadataRoute } from 'next';

export default function robots(): MetadataRoute.Robots {
    return {
        rules: [
            {
                userAgent: '*',
                allow: '/',
                disallow: [
                    '/api/',
                    '/admin/',
                    '/owner/',
                    '/sysadmin/',
                    '/dashboard/',
                    '/settings/',
                    '/login',
                    '/signup',
                    '/checkout',
                    '/ingest/',
                    '/review/',
                    '/compliance/',
                    '/fsma/dashboard',
                    '/fsma/assessment',
                    '/fsma/field-capture',
                    '/fsma/integration',
                    '/pcos/',
                    '/onboarding/',
                    '/accept-invite',
                    '/verify',
                    '/portal/',
                ],
            },
        ],
        sitemap: 'https://www.regengine.co/sitemap.xml',
    };
}
