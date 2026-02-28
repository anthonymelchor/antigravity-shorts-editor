import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # Service Role Key

def create_admin_user(email, password):
    print(f"🚀 Creando usuario administrador: {email}")
    
    # Supabase Auth Admin API endpoint
    url = f"{SUPABASE_URL}/auth/v1/admin/users"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    user_data = {
        "email": email,
        "password": password,
        "email_confirm": True, # Auto-confirm email
        "user_metadata": {"role": "admin"}
    }
    
    with httpx.Client() as client:
        try:
            resp = client.post(url, json=user_data, headers=headers)
            if resp.status_code == 201:
                print(f"✅ Usuario {email} creado con éxito.")
                print(f"🔑 Password: {password}")
            elif resp.status_code == 400 and "already registered" in resp.text:
                print(f"ℹ️ El usuario {email} ya existe.")
            else:
                print(f"❌ Error al crear usuario: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"💥 Error crítico: {e}")

if __name__ == "__main__":
    # Definimos el usuario por defecto solicitado
    ADMIN_EMAIL = "admin@rocotoclip.ai"
    ADMIN_PASS = "Rocoto2026!"
    
    if not SUPABASE_KEY or "secret" not in SUPABASE_KEY:
        print("❌ Error: Necesitas configurar la SUPABASE_KEY (Service Role) en el archivo .env")
    else:
        create_admin_user(ADMIN_EMAIL, ADMIN_PASS)
