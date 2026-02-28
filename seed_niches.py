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

def seed_supabase_accounts():
    print(f"Sincronizando nichos con Supabase: {SUPABASE_URL}")
    accounts_data = [
        {"name": "dominatusmetas_", "niche": "Mentalidad y Éxito Masculino", "keywords": ["mentalidad millonaria", "hábitos de éxito", "disciplina masculina", "finanzas personales"], "target_url": "https://link-to-hotmart.com/dominatus", "platform": "instagram", "user_id": "22dff9c7-9760-4df0-b72c-72d034233576"},
        {"name": "reinventatemujer_", "niche": "Empederamiento y Amor Propio Femenino", "keywords": ["empoderamiento femenino", "amor propio mujer", "glow up mental", "autodisciplina"], "target_url": "https://link-to-hotmart.com/reinventa", "platform": "instagram", "user_id": "22dff9c7-9760-4df0-b72c-72d034233576"},
        {"name": "melchor_ia", "niche": "IA y Futuro", "keywords": ["herramientas IA gratis", "ganar dinero con IA", "noticias IA 2026", "automatización"], "target_url": "https://link-to-hotmart.com/melchor-ia", "platform": "instagram", "user_id": "22dff9c7-9760-4df0-b72c-72d034233576"},
        {"name": "reglas.del.amor", "niche": "Relaciones y Psicología Masc.", "keywords": ["psicología masculina relaciones", "atraer a un hombre", "señales de interés hombres"], "target_url": "https://link-to-hotmart.com/reglas-amor", "platform": "instagram", "user_id": "22dff9c7-9760-4df0-b72c-72d034233576"},
        {"name": "the_manifest_path", "niche": "Manifestación y Espiritualidad", "keywords": ["manifestation techniques", "law of attraction tips", "numerology secret codes"], "target_url": "https://link-to-hotmart.com/manifest", "platform": "instagram", "user_id": "22dff9c7-9760-4df0-b72c-72d034233576"}
    ]
    
    url = f"{SUPABASE_URL}/rest/v1/accounts"
    
    with httpx.Client() as client:
        for acc in accounts_data:
            try:
                # Actualizar nichos existentes por nombre
                url_update = f"{url}?name=eq.{acc['name']}"
                resp = client.patch(
                    url_update, 
                    json=acc, 
                    headers=headers
                )
                if resp.status_code in [200, 204]:
                    print(f"✅ Nicho '{acc['name']}' actualizado/vinculado.")
                else:
                    # Si no existe, intentar insertar
                    resp = client.post(url, json=acc, headers=headers)
                    if resp.status_code in [201, 200, 204]:
                        print(f"✅ Nicho '{acc['name']}' creado.")
                    else:
                        print(f"❌ Error en '{acc['name']}': {resp.status_code} - {resp.text}")
            except Exception as e:
                print(f"💥 Error crítico en '{acc['name']}': {e}")

if __name__ == "__main__":
    seed_supabase_accounts()
