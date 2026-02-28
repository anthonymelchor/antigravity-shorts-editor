import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # Service Role Key

def check_user_status(email):
    print(f"🔍 Buscando estado del usuario: {email}")
    
    # Supabase Auth Admin API to list users
    url = f"{SUPABASE_URL}/auth/v1/admin/users"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    with httpx.Client() as client:
        try:
            # 1. Check in Auth
            resp_auth = client.get(url, headers=headers)
            if resp_auth.status_code == 200:
                users = resp_auth.json().get('users', [])
                user = next((u for u in users if u['email'] == email), None)
                
                if user:
                    print(f"✅ Usuario encontrado en Auth!")
                    print(f"🆔 ID: {user['id']}")
                    print(f"📅 Creado el: {user['created_at']}")
                    
                    # 2. Check in Profiles table
                    profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user['id']}"
                    resp_profile = client.get(profile_url, headers=headers)
                    
                    if resp_profile.status_code == 200 and resp_profile.json():
                        profile = resp_profile.json()[0]
                        print(f"✅ Perfil encontrado en la tabla 'profiles'!")
                        print(f"⏳ Caducidad: {profile.get('subscription_expires_at') or 'Vida Eterna (Ilimitada)'}")
                    else:
                        print(f"⚠️ El usuario tiene cuenta pero NO tiene fila en 'profiles'.")
                        print("Falta ejecutar el SQL del Trigger que te pasé.")
                else:
                    print(f"❌ El usuario {email} no existe en Auth.")
            else:
                print(f"❌ Error al consultar Auth: {resp_auth.status_code} - {resp_auth.text}")
                
        except Exception as e:
            print(f"💥 Error crítico: {e}")

if __name__ == "__main__":
    check_user_status("admin@rocotoclip.ai")
