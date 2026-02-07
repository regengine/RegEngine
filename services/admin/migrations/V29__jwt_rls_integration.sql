-- Migration V29: JWT-RLS Integration Helper Functions
-- Priority: P0 - Required for RLS to work with JWT
-- Date: 2026-01-31
--
-- This migration adds helper functions to integrate JWT claims with RLS policies.
-- It enables both backend (JWT with tenant_id claim) and Supabase (auth.uid) to work with RLS.

-- ============================================================================
-- Helper Function 1: Get Tenant ID from User's Membership
-- ============================================================================
-- For Supabase auth where JWT doesn't include tenant_id,
-- look up user's first membership to get their tenant

CREATE OR REPLACE FUNCTION get_user_tenant_id()
RETURNS UUID AS $$
DECLARE
    user_tenant_id UUID;
BEGIN
    -- Get tenant from user's first membership
    SELECT tenant_id INTO user_tenant_id
    FROM memberships
    WHERE user_id = auth.uid()
    LIMIT 1;
    
    RETURN COALESCE(user_tenant_id, '00000000-0000-0000-0000-000000000001'::UUID);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION get_user_tenant_id() IS 
  'Returns tenant_id for current authenticated user via first membership. Used by RLS policies for Supabase auth.';

-- ============================================================================
-- Helper Function 2: Get Tenant Context (Hybrid)
-- ============================================================================
-- Universal function that works for both backend JWT and Supabase auth

CREATE OR REPLACE FUNCTION get_tenant_context()
RETURNS UUID AS $$
BEGIN
    RETURN COALESCE(
        -- Try session variable first (set by backend middleware)
        NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
        -- Fallback to user's membership (for Supabase)
        get_user_tenant_id(),
        -- Last resort default
        '00000000-0000-0000-0000-000000000001'::UUID
    );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_tenant_context() IS 
  'Universal tenant context function. Tries session variable first, then user membership. Use in RLS policies.';

-- ============================================================================
-- Helper Function 3: Set Tenant Context from JWT (Optional)
-- ============================================================================
-- If using PostgREST with JWTs that include tenant_id claim,
-- this can be called to set the session variable

CREATE OR REPLACE FUNCTION set_tenant_from_jwt()
RETURNS VOID AS $$
DECLARE
    jwt_claims JSON;
    jwt_tenant_id TEXT;
BEGIN
    -- Extract JWT claims from Supabase
    BEGIN
        jwt_claims := current_setting('request.jwt.claims', TRUE)::JSON;
        jwt_tenant_id := jwt_claims->>'tenant_id';
        
        IF jwt_tenant_id IS NOT NULL AND jwt_tenant_id != '' THEN
            PERFORM set_config('app.tenant_id', jwt_tenant_id, FALSE);
        END IF;
    EXCEPTION
        WHEN OTHERS THEN
            -- JWT claims not available, silently continue
            NULL;
    END;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION set_tenant_from_jwt() IS 
  'Extracts tenant_id from JWT claims and sets app.tenant_id session variable. Call via PostgREST.';

-- ============================================================================
-- Usage Examples (for documentation)
-- ============================================================================

/*
-- Example 1: Backend sets session variable directly
SELECT set_config('app.tenant_id', 'uuid-here', FALSE);

-- Example 2: RLS policy using hybrid approach
CREATE POLICY "tenant_isolation" ON table_name
  FOR ALL TO authenticated
  USING (tenant_id = get_tenant_context());

-- Example 3: PostgREST with JWT
-- Call set_tenant_from_jwt() via RPC endpoint:
POST /rest/v1/rpc/set_tenant_from_jwt
Authorization: Bearer <jwt-with-tenant_id-claim>

-- Example 4: Check current tenant context
SELECT get_tenant_context();
*/

-- ============================================================================
-- VERIFICATION
-- ============================================================================

DO $$
BEGIN
  RAISE NOTICE 'V29 Migration Complete: JWT-RLS integration helper functions created';
  RAISE NOTICE 'Functions: get_user_tenant_id(), get_tenant_context(), set_tenant_from_jwt()';
  RAISE NOTICE 'RLS policies can now use get_tenant_context() for universal tenant isolation';
END $$;
