import subprocess
import time
import sys
import os
from sqlalchemy.orm import Session
from models import SessionLocal, DiscoveryResult, Account

class VideoOrchestrator:
    def __init__(self):
        self.db = SessionLocal()

    def get_next_candidate(self):
        """
        Pops the next 'approved' candidate from the database.
        Approved means the user clicked 'Process' in the UI.
        """
        candidate = self.db.query(DiscoveryResult)\
            .filter(DiscoveryResult.status == 'approved')\
            .order_by(DiscoveryResult.views.desc())\
            .first()
        return candidate

    def process_candidate(self, candidate: DiscoveryResult):
        print(f"\n[Orchestrator] Starting processing for: {candidate.title}")
        print(f"[Orchestrator] URL: {candidate.original_url}")
        
        candidate.status = 'processing'
        self.db.commit()
        
        try:
            # We call the existing backend_pipeline.py
            # Generation of a unique version ID
            version_id = str(int(time.time()))
            
            # Use sys.executable to ensure we use the same environment
            process = subprocess.run(
                [sys.executable, "backend_pipeline.py", candidate.original_url, version_id],
                capture_output=True,
                text=True
            )
            
            if process.returncode == 0:
                print(f"[Orchestrator] SUCCESS: {candidate.title} processed.")
                candidate.status = 'completed'
                # Here we could link the output files to the DB record
            else:
                print(f"[Orchestrator] FAILED: Pipeline error.")
                print(f"[Debug-Error] {process.stderr}")
                candidate.status = 'failed'
                
        except Exception as e:
            print(f"[Orchestrator] CRITICAL ERROR: {e}")
            candidate.status = 'failed'
        
        self.db.commit()

    def run_loop(self):
        print("[Orchestrator] System scale active. Monitoring for viral candidates...")
        while True:
            candidate = self.get_next_candidate()
            if candidate:
                self.process_candidate(candidate)
            else:
                print("[Orchestrator] No pending candidates. Sleeping 60s...")
                time.sleep(60)

if __name__ == "__main__":
    orchestrator = VideoOrchestrator()
    orchestrator.run_loop()
