-- =============================================================================
-- MIGRATION: Discovery Engine Data-Driven Architecture
-- Moves ALL search configuration from hardcoded Python to Supabase
-- =============================================================================

-- 1. Add search_config column to accounts table
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS search_config JSONB DEFAULT '{}'::jsonb;

-- 2. Create discovery_settings table for global configuration
CREATE TABLE IF NOT EXISTS discovery_settings (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) DEFAULT NULL,  -- NULL = global default
    setting_key TEXT NOT NULL,
    setting_value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, setting_key)
);

-- 3. Enable RLS on discovery_settings
ALTER TABLE discovery_settings ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (backend reads)
CREATE POLICY "Service role full access" ON discovery_settings
    FOR ALL USING (true) WITH CHECK (true);

-- Allow authenticated users to read global settings and their own overrides
CREATE POLICY "Users can read global settings" ON discovery_settings
    FOR SELECT USING (user_id IS NULL OR user_id = auth.uid());
