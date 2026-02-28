import os
import httpx
from dotenv import load_dotenv

load_dotenv()

def wipe_discovery():
    headers = {
        "apikey": os.getenv("SUPABASE_KEY"),
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}",
        "Content-Type": "application/json"
    }
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/discovery_results?id=gt.0"
    resp = httpx.delete(url, headers=headers)
    print(f"Status: {resp.status_code}")
    if resp.status_code >= 400:
        print(f"Error: {resp.text}")

if __name__ == "__main__":
    wipe_discovery()
