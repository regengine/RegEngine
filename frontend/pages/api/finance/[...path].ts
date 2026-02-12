import { NextApiRequest, NextApiResponse } from 'next';

export const config = {
    api: {
        bodyParser: false,
    },
};

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
    const { path } = req.query;
    const pathStr = Array.isArray(path) ? path.join('/') : path;

    // Target Finance API service
    // Use Docker service name 'finance-api' internally, or localhost if running locally outside docker
    const targetHost = process.env.FINANCE_API_URL || 'http://finance-api:8000';
    const targetUrl = `${targetHost}/v1/finance/${pathStr}${req.url?.split('?')[1] ? '?' + req.url.split('?')[1] : ''}`;

    console.log(`[Finance Proxy] Forwarding ${req.method} to ${targetUrl}`);

    try {
        // Forward the request
        const response = await fetch(targetUrl, {
            method: req.method,
            headers: {
                'Content-Type': 'application/json',
                ...req.headers as any,
                host: new URL(targetHost).host, // Override host header
            },
            body: req.method !== 'GET' && req.method !== 'HEAD' ? req.body : undefined,
            // @ts-ignore - duplexy stuff
            duplex: 'half'
        });

        // Get response body
        const data = await response.arrayBuffer(); // Use arrayBuffer to handle binary if needed, or text
        const buffer = Buffer.from(data);

        // Forward status and headers
        res.status(response.status);
        response.headers.forEach((val, key) => {
            // Skip some headers that might cause issues
            if (key !== 'content-encoding' && key !== 'content-length') {
                res.setHeader(key, val);
            }
        });

        res.send(buffer);

    } catch (error) {
        console.error('[Finance Proxy] Error:', error);
        res.status(502).json({ error: 'Bad Gateway', details: String(error) });
    }
}
