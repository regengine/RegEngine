
CREATE TABLE IF NOT EXISTS public.search_queries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    query TEXT NOT NULL,
    result_count INTEGER DEFAULT 0,
    selected_result TEXT,
    page_url TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for analytics queries
CREATE INDEX IF NOT EXISTS idx_search_queries_query ON public.search_queries (query);
CREATE INDEX IF NOT EXISTS idx_search_queries_created_at ON public.search_queries (created_at DESC);

-- Enable RLS but allow inserts from anon (search is public)
ALTER TABLE public.search_queries ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anonymous search logging" ON public.search_queries
    FOR INSERT TO anon, authenticated
    WITH CHECK (true);

-- Only authenticated users can read analytics
CREATE POLICY "Authenticated users can read search analytics" ON public.search_queries
    FOR SELECT TO authenticated
    USING (true);
;
