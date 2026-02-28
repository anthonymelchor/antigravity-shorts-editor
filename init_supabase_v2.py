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
    sql_commands = """
    -- SQL Schema for Supabase
    -- Run this in the Supabase SQL Editor:
    
    CREATE TABLE IF NOT EXISTS accounts (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        platform TEXT DEFAULT 'instagram',
        niche TEXT NOT NULL,
        keywords JSONB,
        target_url TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

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

    CREATE TABLE IF NOT EXISTS system_status (
        id SERIAL PRIMARY KEY,
        service_name TEXT UNIQUE,
        last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    print("--- 🚨 ACTION REQUIRED 🚨 ---")
    print("Por favor, copia y pega el siguiente SQL en el 'SQL Editor' de tu Dashboard de Supabase:")
    print(sql_commands)
    print("--------------------------------")

def seed_supabase_accounts():
    accounts_data = [
        {"name": "dominatusmetas_", "niche": "Mentalidad y Éxito Masculino", "keywords": ["mentalidad millonaria", "hábitos de éxito", "disciplina masculina", "finanzas personales"], "target_url": "https://link-to-hotmart.com/dominatus", "platform": "instagram"},
        {"name": "reinventatemujer_", "niche": "Empederamiento y Amor Propio Femenino", "keywords": ["empoderamiento femenino", "amor propio mujer", "glow up mental", "autodisciplina"], "target_url": "https://link-to-hotmart.com/reinventa", "platform": "instagram"},
        {"name": "melchor_ia", "niche": "IA y Futuro", "keywords": ["herramientas IA gratis", "ganar dinero con IA", "noticias IA 2026", "automatización"], "target_url": "https://link-to-hotmart.com/melchor-ia", "platform": "instagram"},
        {"name": "reglas.del.amor", "niche": "Relaciones y Psicología Masc.", "keywords": ["psicología masculina relaciones", "atraer a un hombre", "señales de interés hombres"], "target_url": "https://link-to-hotmart.com/reglas-amor", "platform": "instagram"},
        {"name": "the_manifest_path", "niche": "Manifestación y Espiritualidad", "keywords": ["manifestation techniques", "law of attraction tips", "numerology secret codes"], "target_url": "https://link-to-hotmart.com/manifest", "platform": "instagram"}
    ]
    
    url = f"{SUPABASE_URL}/rest/v1/accounts"
    
    with httpx.Client() as client:
        for acc in accounts_data:
            # Upsert using headers
            resp = client.post(
                url, 
                json=acc, 
                headers={**headers, "Prefer": "resolution=merge-duplicates"}
            )
            if resp.status_code in [200, 201]:
                print(f"Account '{acc['name']}' sincronizada con éxito.")
            else:
                print(f"Error en '{acc['name']}': {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    init_supabase_schema()
    # User needs to confirm tables exist first
    input("\nUna vez que hayas ejecutado el SQL en Supabase, presiona ENTER para sembrar los datos...")
    seed_supabase_accounts()
