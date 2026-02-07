# RegEngine Frontend

A modern, smooth Next.js frontend for the RegEngine regulatory intelligence platform.

## Features

✨ **Modern Stack**
- Next.js 15 with App Router
- TypeScript for type safety
- Tailwind CSS for styling
- Framer Motion for smooth animations

🎨 **Beautiful UI**
- Custom component library inspired by shadcn/ui
- Smooth transitions and hover effects
- Responsive design
- Dark mode support

⚡ **Performance**
- React Query for data fetching and caching
- Optimistic updates
- Automatic refetching
- Loading states and skeletons

🔐 **Type-Safe API Client**
- Fully typed API client
- Custom React hooks for all endpoints
- Error handling
- Request/response validation

## Pages

### 🏠 Dashboard (`/`)
- Welcome page with feature overview
- System health status
- Quick navigation to all features
- Industry statistics

### 📄 Document Ingestion (`/ingest`)
- Submit URLs for regulatory document processing
- Real-time ingestion status
- OCR and NLP extraction info

### ✅ Compliance (`/compliance`)
- Browse compliance checklists
- Filter by industry
- Search functionality
- Multi-industry support (Healthcare, Finance, Gaming, Energy, Technology)

### 📊 Opportunities (`/opportunities`)
- Regulatory arbitrage discovery
- Compliance gap analysis
- Jurisdiction comparison
- Filterable results

### 🔑 Admin (`/admin`)
- API key management
- Create/revoke keys
- Secure authentication

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn
- RegEngine backend services running

### Installation

1. **Install dependencies:**
   ```bash
   cd frontend
   npm install
   ```

2. **Configure environment variables:**
   ```bash
   cp .env.example .env.local
   ```

   Edit `.env.local` to match your backend configuration:
   ```env
   NEXT_PUBLIC_API_BASE_URL=http://localhost
   NEXT_PUBLIC_ADMIN_PORT=8400
   NEXT_PUBLIC_INGESTION_PORT=8000
   NEXT_PUBLIC_OPPORTUNITY_PORT=8300
   NEXT_PUBLIC_COMPLIANCE_PORT=8500
   ```

3. **Start the development server:**
   ```bash
   npm run dev
   ```

4. **Open your browser:**
   Navigate to [http://localhost:3000](http://localhost:3000)

## Development

### Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm start` - Start production server
- `npm run lint` - Run ESLint

### Project Structure

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── page.tsx           # Dashboard
│   │   ├── ingest/            # Document ingestion
│   │   ├── compliance/        # Compliance checklists
│   │   ├── opportunities/     # Regulatory opportunities
│   │   ├── admin/             # API key management
│   │   ├── layout.tsx         # Root layout
│   │   └── globals.css        # Global styles
│   ├── components/
│   │   ├── ui/                # UI components
│   │   └── layout/            # Layout components
│   ├── lib/
│   │   ├── api-client.ts      # Type-safe API client
│   │   ├── api-config.ts      # API configuration
│   │   ├── providers.tsx      # React Query provider
│   │   └── utils.ts           # Utility functions
│   ├── hooks/
│   │   └── use-api.ts         # Custom API hooks
│   └── types/
│       └── api.ts             # TypeScript types
├── public/                     # Static assets
├── package.json
├── tsconfig.json
├── tailwind.config.ts
└── next.config.js
```

## API Integration

The frontend integrates with the following RegEngine services:

### Admin Service (Port 8400)
- Health checks
- API key management

### Ingestion Service (Port 8000)
- Document URL submission
- Ingestion status

### Opportunity Service (Port 8300)
- Regulatory arbitrage queries
- Compliance gap analysis

### Compliance Service (Port 8500)
- Checklist browsing
- Configuration validation
- Industry filtering

## Smooth UX Features

### Animations
- Page transitions with Framer Motion
- Card hover effects with scale transforms
- Smooth loading states
- Fade-in animations for content

### Performance Optimizations
- React Query caching (60s stale time)
- Automatic background refetching
- Optimistic updates for mutations
- Request deduplication

### User Experience
- Real-time health monitoring
- Inline error messages
- Success notifications
- Responsive grid layouts
- Accessibility support

## Customization

### Theme Colors
Edit `src/app/globals.css` to customize the color scheme:

```css
:root {
  --primary: 221.2 83.2% 53.3%;
  --secondary: 210 40% 96.1%;
  /* ... more colors */
}
```

### API Configuration
Edit `src/lib/api-config.ts` to change service ports or base URLs.

### Components
All UI components are in `src/components/ui/` and can be customized.

## Production Build

1. **Build the application:**
   ```bash
   npm run build
   ```

2. **Start production server:**
   ```bash
   npm start
   ```

## Deployment

### Docker

Create a `Dockerfile`:

```dockerfile
FROM node:18-alpine AS base

# Install dependencies only when needed
FROM base AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

# Build the application
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# Production image
FROM base AS runner
WORKDIR /app

ENV NODE_ENV production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT 3000

CMD ["node", "server.js"]
```

### Vercel

The easiest way to deploy is using [Vercel](https://vercel.com):

```bash
npm install -g vercel
vercel
```

## Troubleshooting

### Backend Connection Issues
- Ensure all backend services are running
- Check `.env.local` has correct service URLs
- Verify CORS settings on backend

### Build Errors
- Clear Next.js cache: `rm -rf .next`
- Delete node_modules: `rm -rf node_modules && npm install`
- Check TypeScript errors: `npm run lint`

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## License

This project is part of RegEngine and follows the same license.
