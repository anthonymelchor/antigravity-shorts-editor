import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def init_supabase_schema_v4():
    # SQL Schema with Profiles and Subscription Control
    sql_commands = """
    -- 1. Create Profiles table to manage user subscription and roles
    CREATE TABLE IF NOT EXISTS profiles (
        id UUID REFERENCES auth.users ON DELETE CASCADE PRIMARY KEY,
        email TEXT,
        subscription_expires_at TIMESTAMP WITH TIME ZONE DEFAULT NULL, -- NULL = No expiration (Premium/Life)
        is_admin BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- 2. Enable RLS on Profiles
    ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

    -- 3. Policies for Profiles
    DROP POLICY IF EXISTS "Users can view their own profile" ON profiles;
    CREATE POLICY "Users can view their own profile" ON profiles FOR SELECT USING (auth.uid() = id);
    
    DROP POLICY IF EXISTS "Users can update their own profile" ON profiles;
    CREATE POLICY "Users can update their own profile" ON profiles FOR UPDATE USING (auth.uid() = id);

    -- 4. Trigger to automatically create a profile on Signup
    CREATE OR REPLACE FUNCTION public.handle_new_user()
    RETURNS TRIGGER AS $$
    BEGIN
      INSERT INTO public.profiles (id, email)
      VALUES (new.id, new.email);
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql SECURITY DEFINER;

    DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
    CREATE TRIGGER on_auth_user_created
      AFTER INSERT ON auth.users
      FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();

    -- 5. Update existing accounts and discovery tables to use UUID from auth
    -- (If they already exist, we should ensure they have user_id field)
    DO $$ 
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='accounts' AND column_name='user_id') THEN
            ALTER TABLE accounts ADD COLUMN user_id UUID REFERENCES auth.users;
        END IF;
        
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='discovery_results' AND column_name='user_id') THEN
            ALTER TABLE discovery_results ADD COLUMN user_id UUID REFERENCES auth.users;
        END IF;
    END $$;
    """
    
    print("--- 🛡️ SCHEMA V4: CONTROL DE SUSCRIPCIÓN (CLASE MUNDIAL) ---")
    print("Copia y pega este SQL en tu 'SQL Editor' de Supabase para activar los perfiles y la caducidad:")
    print(sql_commands)
    print("----------------------------------------------------------")

if __name__ == "__main__":
    init_supabase_schema_v4()
