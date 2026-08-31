import type { MetadataRoute } from 'next';

/**
 * robots.txt.
 *
 * Sole source of the served robots.txt. A stale `public/robots.txt` used to sit
 * alongside this route and won at request time (static public assets resolve
 * before metadata routes in production), leaving authenticated surfaces such as
 * /admin/, /login, /signup, /ingest/ and /review/ crawlable. Do not reintroduce
 * a static copy — edit the disallow list here.
 */
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
                    '/onboarding/',
                    '/accept-invite',
                    '/verify',
                    '/portal/',
                    '/tools/notice-validator',
                    '/tools/obligation-scanner',
                ],
            },
        ],
        sitemap: 'https://regengine.co/sitemap.xml',
    };
}
