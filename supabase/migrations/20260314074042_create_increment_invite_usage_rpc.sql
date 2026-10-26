
CREATE OR REPLACE FUNCTION public.increment_invite_usage(code_id uuid)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
AS $$
    UPDATE public.developer_invite_codes
    SET used_count = used_count + 1
    WHERE id = code_id;
$$;
;
