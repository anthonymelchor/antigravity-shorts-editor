import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

def init_supabase_schema():
    # SQL Schema with Multi-user support
    sql_commands = """
    -- Enable Vector extension for future RAG
    CREATE EXTENSION IF NOT EXISTS vector;

    -- Update accounts table with user_id
    CREATE TABLE IF NOT EXISTS accounts (
        id SERIAL PRIMARY KEY,
        user_id UUID DEFAULT auth.uid(), -- Multi-user association
        name TEXT UNIQUE NOT NULL,
        platform TEXT DEFAULT 'instagram',
        niche TEXT NOT NULL,
        keywords JSONB,
        target_url TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Update discovery_results with user_id
    CREATE TABLE IF NOT EXISTS discovery_results (
        id SERIAL PRIMARY KEY,
        user_id UUID DEFAULT auth.uid(),
        account_id INTEGER REFERENCES accounts(id),
        title TEXT,
        original_url TEXT UNIQUE NOT NULL,
        platform TEXT DEFAULT 'youtube',
        views BIGINT DEFAULT 0,
        duration INTEGER DEFAULT 0,
        discovery_score FLOAT DEFAULT 0.0,
        status TEXT DEFAULT 'discovered',
        content_type TEXT DEFAULT 'value',
        metadata_json JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Enable Row Level Security (RLS)
    ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
    ALTER TABLE discovery_results ENABLE ROW LEVEL SECURITY;

    -- Policies: Only the owner can see their data
    CREATE POLICY "Users can view their own accounts" ON accounts FOR SELECT USING (auth.uid() = user_id);
    CREATE POLICY "Users can insert their own accounts" ON accounts FOR INSERT WITH CHECK (auth.uid() = user_id);
    CREATE POLICY "Users can update their own accounts" ON accounts FOR UPDATE USING (auth.uid() = user_id);

    CREATE POLICY "Users can view their own discovery results" ON discovery_results FOR SELECT USING (auth.uid() = user_id);
    CREATE POLICY "Users can insert their own discovery results" ON discovery_results FOR INSERT WITH CHECK (auth.uid() = user_id);
    
    -- System status stays public for administrative monitoring
    CREATE TABLE IF NOT EXISTS system_status (
        id SERIAL PRIMARY KEY,
        service_name TEXT UNIQUE,
        last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    print("--- 🛡️ SCHEMA MULTI-USUARIO (CLASE MUNDIAL) ---")
    print("Copia y pega este SQL en el Editor de Supabase para activar la seguridad por usuario:")
    print(sql_commands)
    print("-----------------------------------------------")

if __name__ == "__main__":
    init_supabase_schema()
