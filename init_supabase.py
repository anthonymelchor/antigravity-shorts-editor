import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def init_supabase_schema():
    """
    Instructions for the user: 
    Run these SQL commands in your Supabase SQL Editor to create the tables.
    """
    sql_commands = """
    -- Create accounts table
    CREATE TABLE IF NOT EXISTS accounts (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        platform TEXT DEFAULT 'instagram',
        niche TEXT NOT NULL,
        keywords JSONB,
        target_url TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Create discovery_results table
    CREATE TABLE IF NOT EXISTS discovery_results (
        id SERIAL PRIMARY KEY,
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

    -- Create system_status table
    CREATE TABLE IF NOT EXISTS system_status (
        id SERIAL PRIMARY KEY,
        service_name TEXT UNIQUE,
        last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    print("--- SQL SCHEMA TO RUN IN SUPABASE SQL EDITOR ---")
    print(sql_commands)
    print("-----------------------------------------------")

def seed_supabase_accounts():
    accounts_data = [
        {"name": "dominatusmetas_", "niche": "Mentalidad y Éxito Masculino", "keywords": ["mentalidad millonaria", "hábitos de éxito", "disciplina masculina", "finanzas personales"], "target_url": "https://link-to-hotmart.com/dominatus", "platform": "instagram"},
        {"name": "reinventatemujer_", "niche": "Empederamiento y Amor Propio Femenino", "keywords": ["empoderamiento femenino", "amor propio mujer", "glow up mental", "autodisciplina"], "target_url": "https://link-to-hotmart.com/reinventa", "platform": "instagram"},
        {"name": "melchor_ia", "niche": "IA y Futuro", "keywords": ["herramientas IA gratis", "ganar dinero con IA", "noticias IA 2026", "automatización"], "target_url": "https://link-to-hotmart.com/melchor-ia", "platform": "instagram"},
        {"name": "reglas.del.amor", "niche": "Relaciones y Psicología Masc.", "keywords": ["psicología masculina relaciones", "atraer a un hombre", "señales de interés hombres"], "target_url": "https://link-to-hotmart.com/reglas-amor", "platform": "instagram"},
        {"name": "the_manifest_path", "niche": "Manifestación y Espiritualidad", "keywords": ["manifestation techniques", "law of attraction tips", "numerology secret codes"], "target_url": "https://link-to-hotmart.com/manifest", "platform": "instagram"}
    ]
    
    for acc in accounts_data:
        try:
            supabase.table("accounts").upsert(acc, on_conflict="name").execute()
            print(f"Account '{acc['name']}' seeded/updated.")
        except Exception as e:
            print(f"Error seeding account '{acc['name']}': {e}")

if __name__ == "__main__":
    init_supabase_schema()
    # Note: User needs to run SQL first if tables don't exist
    # But often we can try to seed directly if tables are there.
    seed_supabase_accounts()
