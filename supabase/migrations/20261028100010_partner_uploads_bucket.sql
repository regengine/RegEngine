-- Private Supabase Storage bucket for partner Beta uploads.
--
-- Layout: partner-uploads/{tenant_id}/{engagement_id}/{partner_file_id}
-- Private (not public). No anonymous list/read. MIME allowlist CSV-oriented.
-- Client UPDATE/DELETE on storage.objects is denied; retention uses service
-- role / SECURITY DEFINER. Folder[1] must equal live tenant context.
--
-- Supabase-only (storage schema). Not mirrored on Railway Postgres.
-- Idempotent. Do not apply to prod without C.Lee yes.

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'partner-uploads',
    'partner-uploads',
    false,
    26214400,  -- 25 MiB Beta cap
    ARRAY[
        'text/csv',
        'application/csv',
        'text/plain',
        'application/vnd.ms-excel'
    ]::text[]
)
ON CONFLICT (id) DO UPDATE
SET
    public = EXCLUDED.public,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

-- storage.objects RLS for this bucket. CASE + get_tenant_context (not JWT).
DROP POLICY IF EXISTS partner_uploads_select_own ON storage.objects;
CREATE POLICY partner_uploads_select_own ON storage.objects
    FOR SELECT
    TO authenticated
    USING (
        bucket_id = 'partner-uploads'
        AND (storage.foldername(name))[1] = (select public.get_tenant_context())::text
    );

DROP POLICY IF EXISTS partner_uploads_insert_own ON storage.objects;
CREATE POLICY partner_uploads_insert_own ON storage.objects
    FOR INSERT
    TO authenticated
    WITH CHECK (
        bucket_id = 'partner-uploads'
        AND (storage.foldername(name))[1] = (select public.get_tenant_context())::text
    );

-- Explicitly no UPDATE/DELETE policies for authenticated on this bucket.
DROP POLICY IF EXISTS partner_uploads_update_own ON storage.objects;
DROP POLICY IF EXISTS partner_uploads_delete_own ON storage.objects;

-- Downgrade (run by hand only):
--
-- DROP POLICY IF EXISTS partner_uploads_insert_own ON storage.objects;
-- DROP POLICY IF EXISTS partner_uploads_select_own ON storage.objects;
-- DELETE FROM storage.objects WHERE bucket_id = 'partner-uploads';
-- DELETE FROM storage.buckets WHERE id = 'partner-uploads';
