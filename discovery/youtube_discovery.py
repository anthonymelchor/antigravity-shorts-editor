import os
import sys
import json
import httpx
import time
import yt_dlp
from dotenv import load_dotenv

# Add parent directory to sys.path for local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # Service Role Key
# SECURITY: Removed hardcoded ADMIN_USER_ID fallback
# All discovery results MUST have a valid user_id from their account

class ContentDiscoveryEngine:
    """
    RocotoClip High-Precision Content Discovery Engine.
    Designed for World-Class Scale & Performance.
    """
    def __init__(self):
        self.headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'skip_download': True,
        }

    def _log(self, status, message, progress=None):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        prog_str = f" [{progress}%]" if progress is not None else ""
        log_msg = f"[{timestamp}] [{status}]{prog_str} {message}"
        print(log_msg)
        try:
            # We use a dedicated log for discovery to separate it from pipeline processing
            with open("discovery.log", "a", encoding="utf-8") as f:
                f.write(log_msg + "\n")
        except: pass

    def fetch_accounts_from_supabase(self, user_id=None):
        url = f"{SUPABASE_URL}/rest/v1/accounts?select=*"
        if user_id:
            url += f"&user_id=eq.{user_id}"
        
        with httpx.Client() as client:
            resp = client.get(url, headers=self.headers)
            if resp.status_code == 200:
                return resp.json()
            else:
                self._log("ERROR", f"Failed to fetch accounts: {resp.status_code} - {resp.text}")
                return []

    def search_viral_content(self, account, max_results=5):
        # ... (rest of the function remains the same)
        self._log("START", f"Scanning niche: {account['niche']} for user {account.get('user_id', 'Unknown')}", 0)
        
        # Calculate date 3 years ago (YYYYMMDD)
        from datetime import datetime, timedelta
        three_years_ago = (datetime.now() - timedelta(days=3*365)).strftime('%Y%m%d')
        
        search_opts = {
            **self.ydl_opts,
            'extract_flat': False,
            'force_generic_extractor': False,
            'dateafter': three_years_ago, # ONLY videos from the last 3 years
        }

        blacklist = ["music", "meditation", "relaxing", "song", "playlist", "binaural", "frecuencia", "asmr", "sleep", "gaming", "fortnite", "minecraft"]
        new_count = 0
        keywords = account.get('keywords', [])
        
        all_candidates = []
        for i, keyword in enumerate(keywords):
            progress = int((i / len(keywords)) * 100)
            self._log("PROGRESS", f"Sampling: '{keyword}'...", progress)
            
            # Request a much larger sample from YouTube for each keyword to filter the elite
            sample_size = 20
            refined_query = f"ytsearch{sample_size}:{keyword} podcast entrevista charla" 
            
            try:
                with yt_dlp.YoutubeDL(search_opts) as ydl:
                    info = ydl.extract_info(refined_query, download=False)
                    if 'entries' in info:
                        for entry in info['entries']:
                            if not entry: continue
                            url = entry.get('webpage_url') or entry.get('url')
                            if not url: continue
                            
                            title = entry.get('title', '').lower()
                            views = entry.get('view_count', 0)
                            duration = entry.get('duration', 0)

                            # --- WORLD-CLASS FILTERS (Efficiency) ---
                            if views < 30000: continue # Minimum floor
                            if duration < 480 or duration > 7200: continue # 8m to 2h 
                            if any(word in title for word in blacklist): continue # Content control

                            all_candidates.append({
                                "entry": entry,
                                "views": views,
                                "duration": duration
                            })
                time.sleep(1) # Network courtesy
            except Exception as e:
                self._log("WARNING", f"Error sampling '{keyword}': {e}")

        # --- VIRAL-FIRST RANKING ---
        # Sort all discovered videos across all keywords by popularity (descending)
        all_candidates.sort(key=lambda x: x['views'], reverse=True)
        
        # Select and save only the top elite
        final_selection = all_candidates[:max_results]
        
        for item in final_selection:
            self._save_candidate(account, item['entry'], item['views'], item['duration'])
            new_count += 1

        self._log("END", f"Added {new_count} candidates for {account['name']}.", 100)

    def _save_candidate(self, account, entry, views, duration):
        # SECURITY: Require user_id — skip accounts without one
        user_id = account.get("user_id")
        if not user_id:
            self._log("WARNING", f"Skipping candidate save: account {account['id']} has no user_id")
            return
        
        url = f"{SUPABASE_URL}/rest/v1/discovery_results"
        payload = {
            "user_id": user_id,
            "account_id": account["id"],
            "title": entry.get('title'),
            "original_url": entry.get('webpage_url') or entry.get('url'),
            "views": views,
            "duration": duration,
            "status": "discovered",
            "metadata_json": {
                "uploader": entry.get("uploader"),
                "upload_date": entry.get("upload_date"),
                "description": entry.get("description", "")[:500]
            }
        }
        
        with httpx.Client() as client:
            # Use Resolution=Merge-Duplicates (Upsert)
            # This ensures no duplicates if URL exists
            resp = client.post(
                url, 
                json=payload, 
                headers={**self.headers, "Prefer": "resolution=merge-duplicates"}
            )
            if resp.status_code not in [200, 201]:
                # 409 is expected if UNIQUE constraint triggers and no merge is supported by the specific endpoint
                # but typically Supabase REST handles it with resolution=merge-duplicates
                pass

    def run_cycle(self, limit_per_niche=5, user_id=None):
        self._log("SYSTEM", f"Starting Manual Discovery Life-Cycle (Limit: {limit_per_niche} per niche, User: {user_id or 'All'})...")
        accounts = self.fetch_accounts_from_supabase(user_id=user_id)
        if not accounts:
            self._log("SYSTEM", "No active accounts to scan.")
            return

        for acc in accounts:
            self.search_viral_content(acc, max_results=limit_per_niche)
        
        self._log("SYSTEM", "Discovery Life-Cycle Completed.")

if __name__ == "__main__":
    limit = 5
    if len(sys.argv) > 1:
        try: limit = int(sys.argv[1])
        except: pass
    
    engine = ContentDiscoveryEngine()
    engine.run_cycle(limit_per_niche=limit)
