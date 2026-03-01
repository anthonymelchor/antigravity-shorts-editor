"""
=============================================================================
MOTOR DE INVESTIGACIÓN DE CONTENIDO LARGO — HIGH-INTENSITY DISCOVERY ENGINE
=============================================================================
Scout de contenido viral de alto rendimiento para cuentas faceless.
Prioriza tensión emocional, controversia, diagnóstico humano y potencial
de debate. CALIDAD > VELOCIDAD.

ALL CONFIGURATION IS DATA-DRIVEN FROM SUPABASE:
  - Per-account: accounts.search_config (search terms, formats, filter overrides)
  - Global: discovery_settings table (blacklist, tension keywords, thresholds)

Based on: PROMPT MAESTRO — MOTOR DE INVESTIGACIÓN DE CONTENIDO LARGO
=============================================================================
"""

import os
import sys
import re
import json
import httpx
import time
import yt_dlp
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


class ContentDiscoveryEngine:
    """
    Motor de Investigación de Contenido Largo — High-Intensity Discovery Engine.

    ALL configuration is loaded from Supabase at runtime:
    - accounts.search_config: per-account search terms, formats, filter overrides
    - discovery_settings: global config (blacklist, tension keywords, thresholds)

    Scalable per user — each user's accounts carry their own config.
    QUALITY > SPEED.
    """

    def __init__(self):
        self.headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        self.ydl_base_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        # Config cache (loaded once per cycle)
        self._global_config = None

    # ================================================================
    # LOGGING
    # ================================================================
    def _log(self, status, message, progress=None):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        prog_str = f" [{progress}%]" if progress is not None else ""
        log_msg = f"[{timestamp}] [{status}]{prog_str} {message}"
        print(log_msg)
        try:
            with open("discovery.log", "a", encoding="utf-8") as f:
                f.write(log_msg + "\n")
        except:
            pass

    # ================================================================
    # CONFIGURATION LOADING (from Supabase)
    # ================================================================
    def _load_global_config(self):
        """
        Loads global discovery settings from Supabase (discovery_settings table).
        These are shared across all users (user_id IS NULL).
        Cached per cycle for efficiency.
        """
        if self._global_config is not None:
            return self._global_config

        self._log("CONFIG", "Loading global discovery settings from Supabase...")
        url = f"{SUPABASE_URL}/rest/v1/discovery_settings?select=setting_key,setting_value&user_id=is.null"

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    rows = resp.json()
                    config = {}
                    for row in rows:
                        config[row["setting_key"]] = row["setting_value"]
                    self._global_config = config
                    self._log("CONFIG", f"Loaded {len(config)} global settings: {', '.join(config.keys())}")
                    return config
                else:
                    self._log("ERROR", f"Failed to load global config: {resp.status_code}")
        except Exception as e:
            self._log("ERROR", f"Config load exception: {str(e)[:100]}")

        # Minimal fallback if DB is unreachable
        self._log("WARNING", "Using minimal fallback config — DB unreachable")
        self._global_config = {}
        return self._global_config

    def _load_user_overrides(self, user_id):
        """
        Loads user-specific overrides from discovery_settings (if any).
        These override the global defaults for this specific user.
        """
        url = f"{SUPABASE_URL}/rest/v1/discovery_settings?select=setting_key,setting_value&user_id=eq.{user_id}"
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    rows = resp.json()
                    overrides = {}
                    for row in rows:
                        overrides[row["setting_key"]] = row["setting_value"]
                    if overrides:
                        self._log("CONFIG", f"Loaded {len(overrides)} user-specific overrides for {user_id}")
                    return overrides
        except:
            pass
        return {}

    def _get_config(self, key, user_id=None):
        """
        Gets a config value with user override priority:
        1. User-specific override (if exists)
        2. Global default
        3. Empty fallback
        """
        global_config = self._load_global_config()

        if user_id:
            if not hasattr(self, '_user_overrides'):
                self._user_overrides = {}
            if user_id not in self._user_overrides:
                self._user_overrides[user_id] = self._load_user_overrides(user_id)

            user_config = self._user_overrides.get(user_id, {})
            if key in user_config:
                return user_config[key]

        return global_config.get(key, None)

    def _get_filters(self, account):
        """
        Gets filter thresholds for an account.
        Priority: account.search_config.filters > user overrides > global defaults
        """
        # Check account-level overrides first
        search_config = account.get("search_config", {}) or {}
        account_filters = search_config.get("filters", {})

        # Get global defaults
        user_id = account.get("user_id")
        global_defaults = self._get_config("default_filters", user_id) or {}

        # Merge: account overrides > global defaults > hardcoded safety fallback
        safety_fallback = {
            "duration_min": 720,
            "duration_max": 7200,
            "min_views": 25000,
            "min_comments": 80,
            "min_comment_ratio": 0.015,
            "min_tension_score": 4,
            "min_video_score": 7,
        }

        merged = {**safety_fallback, **global_defaults, **account_filters}
        return merged

    # ================================================================
    # SUPABASE DATA ACCESS
    # ================================================================
    def fetch_accounts_from_supabase(self, user_id=None):
        url = f"{SUPABASE_URL}/rest/v1/accounts?select=*"
        if user_id:
            url += f"&user_id=eq.{user_id}"

        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=self.headers)
            if resp.status_code == 200:
                return resp.json()
            else:
                self._log("ERROR", f"Failed to fetch accounts: {resp.status_code} - {resp.text}")
                return []

    def _get_existing_urls(self, user_id):
        """Fetch all existing URLs for this user to avoid re-processing."""
        url = f"{SUPABASE_URL}/rest/v1/discovery_results?select=original_url&user_id=eq.{user_id}"
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    return {r["original_url"] for r in resp.json()}
        except:
            pass
        return set()

    def _save_candidate(self, account, candidate_data):
        """Save a fully scored and classified candidate to Supabase."""
        user_id = account.get("user_id")
        if not user_id:
            self._log("WARNING", f"Skipping save: account {account['id']} has no user_id")
            return

        url = f"{SUPABASE_URL}/rest/v1/discovery_results"
        payload = {
            "user_id": user_id,
            "account_id": account["id"],
            "title": candidate_data["title"],
            "original_url": candidate_data["url"],
            "views": candidate_data["views"],
            "duration": candidate_data["duration"],
            "status": "discovered",
            "platform": "youtube",
            "content_type": ",".join(candidate_data.get("classification", ["value"])),
            "discovery_score": candidate_data.get("video_score", 0),
            "metadata_json": {
                "uploader": candidate_data.get("uploader", ""),
                "upload_date": candidate_data.get("upload_date", ""),
                "description": candidate_data.get("description", "")[:1000],
                "tension_score": candidate_data.get("tension_score", 0),
                "comment_score": candidate_data.get("comment_score", 0),
                "description_score": candidate_data.get("description_score", 0),
                "video_score": candidate_data.get("video_score", 0),
                "classification": candidate_data.get("classification", []),
                "strategic_reasoning": candidate_data.get("strategic_reasoning", ""),
                "comment_count": candidate_data.get("comment_count", 0),
                "comment_ratio": candidate_data.get("comment_ratio", 0.0),
                "top_comments": candidate_data.get("top_comments", []),
                "tension_breakdown": candidate_data.get("tension_breakdown", {}),
            },
        }

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                url,
                json=payload,
                headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
            )
            if resp.status_code in [200, 201]:
                self._log("SAVED", f"✅ [{candidate_data.get('video_score', 0):.1f}] {candidate_data['title'][:60]}")
            else:
                self._log("DB-ERROR", f"Save failed: {resp.status_code} - {resp.text[:200]}")

    # ================================================================
    # TENSION SCORE — Title Analysis (Data-Driven from Supabase)
    # ================================================================
    def _calculate_tension_score(self, title, user_id=None):
        """
        Assigns a TENSION SCORE of 0-10 to a video title.
        Keywords and weights loaded from discovery_settings.tension_keywords.
        """
        tension_config = self._get_config("tension_keywords", user_id)
        if not tension_config:
            return 0, {}

        title_lower = title.lower()
        score = 0
        breakdown = {}

        for category, config in tension_config.items():
            cat_score = config.get("score", 1)
            words = config.get("words", [])
            for word in words:
                if word.lower() in title_lower:
                    score += cat_score
                    breakdown[category] = breakdown.get(category, 0) + cat_score
                    break  # Only count each category once per title

        return min(score, 10), breakdown

    # ================================================================
    # DESCRIPTION SCORE — Description Analysis (Data-Driven)
    # ================================================================
    def _calculate_description_score(self, description, user_id=None):
        """
        Scores the video description (0-10).
        Categories and keywords loaded from discovery_settings.description_scoring.
        """
        if not description:
            return 0

        desc_config = self._get_config("description_scoring", user_id)
        if not desc_config:
            return 0

        desc_lower = description.lower()
        score = 0

        for category, config in desc_config.items():
            cat_score = config.get("score", 1)
            words = config.get("words", [])
            if any(w in desc_lower for w in words):
                score += cat_score

        # Bonus: Detailed description (+1)
        if len(description) > 300:
            score += 1

        # Bonus: Timestamps in description (+1)
        if re.search(r'\d{1,2}:\d{2}', description):
            score += 1

        return min(score, 10)

    # ================================================================
    # COMMENT SCORE — Comment Quality Analysis (Data-Driven)
    # ================================================================
    def _analyze_comments(self, video_url, user_id=None):
        """
        Extracts top comments and calculates COMMENT_SCORE.
        Emotional keywords and spam indicators loaded from Supabase.
        """
        emotional_keywords = self._get_config("emotional_comment_keywords", user_id) or []
        spam_indicators = self._get_config("spam_indicators", user_id) or []

        try:
            comment_opts = {
                **self.ydl_base_opts,
                "getcomments": True,
                "extractor_args": {"youtube": {"max_comments": ["20", "0", "0", "20"]}},
            }

            with yt_dlp.YoutubeDL(comment_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

            comments_raw = info.get("comments", [])
            view_count = info.get("view_count", 1)
            comment_count_total = info.get("comment_count", len(comments_raw))
            comment_ratio = comment_count_total / max(view_count, 1)

            # Sort by likes, take top 20
            comments_sorted = sorted(comments_raw, key=lambda c: c.get("like_count", 0), reverse=True)
            top_comments = [
                {"text": c.get("text", "")[:300], "likes": c.get("like_count", 0), "author": c.get("author", "")[:50]}
                for c in comments_sorted[:20]
            ]

            # ---- SCORING ----
            score = 0

            # Ratio scoring
            if comment_ratio >= 0.03:
                score += 3
            elif comment_ratio >= 0.015:
                score += 2
            elif comment_ratio >= 0.005:
                score += 1

            if comment_count_total >= 80:
                score += 1

            # Quality analysis
            emotional_hits = 0
            timestamp_comments = 0
            long_comments = 0
            debate_signals = 0

            debate_words = ["no estoy de acuerdo", "disagree", "pero", "sin embargo",
                           "depende", "no siempre", "en mi experiencia"]

            for c in top_comments:
                text = c.get("text", "").lower()
                if any(kw in text for kw in emotional_keywords):
                    emotional_hits += 1
                if re.search(r'\d{1,2}:\d{2}', text):
                    timestamp_comments += 1
                if len(text) > 100:
                    long_comments += 1
                if any(d in text for d in debate_words):
                    debate_signals += 1

            n = len(top_comments) if top_comments else 1
            if emotional_hits / n >= 0.3:
                score += 2
            if timestamp_comments >= 2:
                score += 1
            if long_comments / n >= 0.4:
                score += 1
            if debate_signals >= 2:
                score += 1

            # Penalties
            spam_count = sum(1 for c in top_comments if any(s in c.get("text", "").lower() for s in spam_indicators))
            if spam_count / n >= 0.5:
                score = max(0, score - 3)

            emoji_only = sum(1 for c in top_comments if len(c.get("text", "").strip()) < 10)
            if emoji_only / n >= 0.5:
                score = max(0, score - 2)

            return comment_count_total, comment_ratio, min(score, 10), top_comments

        except Exception as e:
            self._log("WARNING", f"Comment extraction failed: {str(e)[:100]}")
            return 0, 0.0, 0, []

    # ================================================================
    # VIDEO CLASSIFICATION (Data-Driven)
    # ================================================================
    def _classify_video(self, title, description, top_comments):
        """Classifies a video as EXPLOSION, AUTORIDAD, and/or CONVERSION (max 2)."""
        title_lower = (title or "").lower()
        desc_lower = (description or "").lower()
        comments_text = " ".join(c.get("text", "") for c in top_comments).lower()
        all_text = f"{title_lower} {desc_lower} {comments_text}"

        classifications = []

        explosion_signals = ["polém", "debate", "controv", "pelea", "enfrent",
                           "no estoy de acuerdo", "confronta", "brutal", "duro",
                           "raw", "uncensored", "heated", "fight", "clash"]
        if sum(1 for w in explosion_signals if w in all_text) >= 2:
            classifications.append("EXPLOSION")

        authority_signals = ["experto", "expert", "framework", "método", "method",
                           "estructura", "paso a paso", "step by step", "masterclass",
                           "gracias", "thank", "aprendí", "learned", "dr.", "doctor",
                           "profesor", "coach", "autor", "author", "libro", "book"]
        if sum(1 for w in authority_signals if w in all_text) >= 2:
            classifications.append("AUTORIDAD")

        conversion_signals = ["error", "mistake", "señal", "signal", "red flag",
                            "problema", "problem", "solución", "solution",
                            "diagnóstico", "diagnosis", "identificar", "identify",
                            "cómo saber", "how to know", "cómo evitar", "how to avoid"]
        if sum(1 for w in conversion_signals if w in all_text) >= 2:
            classifications.append("CONVERSION")

        return classifications[:2] if classifications else ["AUTORIDAD"]

    # ================================================================
    # STRATEGIC REASONING
    # ================================================================
    def _generate_reasoning(self, candidate_data):
        parts = []
        ts = candidate_data.get("tension_score", 0)
        clsf = candidate_data.get("classification", [])
        cr = candidate_data.get("comment_ratio", 0)

        if ts >= 6:
            parts.append(f"Título con alta tensión emocional ({ts}/10)")
        elif ts >= 4:
            parts.append(f"Título con tensión moderada ({ts}/10)")
        if cr >= 0.015:
            parts.append(f"Ratio comentarios/vistas excelente ({cr:.2%})")
        if "EXPLOSION" in clsf:
            parts.append("Alto potencial de viralidad explosiva y debate")
        if "CONVERSION" in clsf:
            parts.append("Contiene diagnóstico/errores explotables para CTA indirecto")

        return ". ".join(parts[:3]) + "." if parts else "Candidato estándar."

    # ================================================================
    # MASTER SEARCH (Data-Driven from Supabase)
    # ================================================================
    def search_viral_content(self, account, max_results=5):
        """
        High-intensity content search. Quality over speed.
        
        ALL config read from:
        - account['search_config'] → search terms, formats, filter overrides
        - discovery_settings → global blacklist, tension keywords, thresholds
        """
        niche = account.get("niche", "")
        user_id = account.get("user_id", "Unknown")
        search_config = account.get("search_config", {}) or {}
        self._log("START", f"🔍 Scanning niche: {niche} for user {user_id}", 0)

        # Get search terms and formats from account's search_config (from Supabase)
        search_terms = search_config.get("search_terms", [])
        formats = search_config.get("search_formats", [])

        if not search_terms:
            self._log("WARNING", f"Account '{account.get('name')}' has NO search_terms in search_config. "
                                 f"Configure them in Supabase → accounts → search_config.")
            # Fall back to legacy keywords column if available
            search_terms = account.get("keywords", [])
            if not search_terms:
                self._log("ERROR", f"No search terms found at all for account '{account.get('name')}'. Skipping.")
                return

        if not formats:
            formats = ["podcast", "debate", "entrevista"]
            self._log("WARNING", f"No search_formats configured. Using defaults: {formats}")

        # Get filters (account override > user override > global default)
        filters = self._get_filters(account)
        self._log("CONFIG", f"Filters: views≥{filters['min_views']}, comments≥{filters['min_comments']}, "
                           f"ratio≥{filters['min_comment_ratio']}, tension≥{filters['min_tension_score']}, "
                           f"video_score≥{filters['min_video_score']}")

        # Get content blacklist from global config
        content_blacklist = self._get_config("content_blacklist", user_id) or []

        # Date filter
        three_years_ago = (datetime.now() - timedelta(days=3 * 365)).strftime("%Y%m%d")
        search_opts = {
            **self.ydl_base_opts,
            "extract_flat": False,
            "force_generic_extractor": False,
            "dateafter": three_years_ago,
        }

        existing_urls = self._get_existing_urls(user_id)
        self._log("INFO", f"Found {len(existing_urls)} existing URLs to skip")

        # === PHASE 1: Broad Discovery ===
        raw_candidates = []
        total_searches = len(search_terms) * len(formats[:2])
        search_idx = 0

        for term in search_terms:
            for fmt in formats[:2]:
                search_idx += 1
                progress = int((search_idx / total_searches) * 60)
                query_string = f"{term} {fmt}"
                self._log("SEARCH", f"[{search_idx}/{total_searches}] '{query_string}'", progress)

                sample_size = 15
                refined_query = f"ytsearch{sample_size}:{query_string}"

                try:
                    with yt_dlp.YoutubeDL(search_opts) as ydl:
                        info = ydl.extract_info(refined_query, download=False)
                        if "entries" not in info:
                            continue

                        for entry in info["entries"]:
                            if not entry:
                                continue
                            url = entry.get("webpage_url") or entry.get("url")
                            if not url or url in existing_urls:
                                continue

                            title = entry.get("title", "")
                            title_lower = title.lower()
                            views = entry.get("view_count", 0)
                            duration = entry.get("duration", 0)
                            description = entry.get("description", "")

                            # === FILTER 1: Duration ===
                            if duration < filters["duration_min"] or duration > filters["duration_max"]:
                                continue

                            # === FILTER 2: Minimum views ===
                            if views < filters["min_views"]:
                                continue

                            # === FILTER 3: Blacklist ===
                            if any(word in title_lower for word in content_blacklist):
                                continue

                            # === FILTER 4: TENSION_SCORE ===
                            tension_score, tension_breakdown = self._calculate_tension_score(title, user_id)
                            if tension_score < filters["min_tension_score"]:
                                self._log("REJECT", f"Low tension ({tension_score}): {title[:50]}")
                                continue

                            # === FILTER 5: DESCRIPTION_SCORE ===
                            description_score = self._calculate_description_score(description, user_id)

                            raw_candidates.append({
                                "url": url, "title": title, "views": views,
                                "duration": duration, "description": description,
                                "uploader": entry.get("uploader", ""),
                                "upload_date": entry.get("upload_date", ""),
                                "tension_score": tension_score,
                                "tension_breakdown": tension_breakdown,
                                "description_score": description_score,
                                "search_term": query_string,
                            })
                            existing_urls.add(url)

                    time.sleep(1.5)
                except Exception as e:
                    self._log("WARNING", f"Search error: '{query_string}': {str(e)[:80]}")

        # Deduplicate
        seen = set()
        raw_candidates = [c for c in raw_candidates if c["url"] not in seen and not seen.add(c["url"])]

        self._log("PHASE1", f"Found {len(raw_candidates)} candidates passing basic filters", 60)

        if not raw_candidates:
            self._log("END", "NO HIGH-INTENSITY VIDEOS FOUND — all candidates rejected by filters", 100)
            return

        raw_candidates.sort(key=lambda x: (x["tension_score"], x["views"]), reverse=True)

        # === PHASE 2: Deep Analysis (Comments) ===
        max_deep = min(len(raw_candidates), max_results * 3)
        self._log("PHASE2", f"Deep-analyzing top {max_deep} candidates (comments)...", 65)

        scored_candidates = []
        for idx, candidate in enumerate(raw_candidates[:max_deep]):
            progress = 65 + int((idx / max_deep) * 30)
            self._log("DEEP", f"[{idx+1}/{max_deep}] {candidate['title'][:50]}...", progress)

            comment_count, comment_ratio, comment_score, top_comments = self._analyze_comments(
                candidate["url"], user_id
            )

            if comment_count < filters["min_comments"]:
                self._log("REJECT", f"Low comments ({comment_count}): {candidate['title'][:50]}")
                continue

            if comment_ratio < filters["min_comment_ratio"]:
                self._log("REJECT", f"Low ratio ({comment_ratio:.4f}): {candidate['title'][:50]}")
                continue

            video_score = candidate["tension_score"] + comment_score + candidate["description_score"]

            if video_score < filters["min_video_score"]:
                self._log("REJECT", f"Low video score ({video_score:.1f}): {candidate['title'][:50]}")
                continue

            classification = self._classify_video(candidate["title"], candidate["description"], top_comments)

            candidate.update({
                "comment_count": comment_count, "comment_ratio": comment_ratio,
                "comment_score": comment_score, "video_score": video_score,
                "classification": classification, "top_comments": top_comments,
            })
            candidate["strategic_reasoning"] = self._generate_reasoning(candidate)
            scored_candidates.append(candidate)

            self._log("APPROVED",
                      f"✅ Score={video_score:.1f} [{'/'.join(classification)}] "
                      f"T={candidate['tension_score']} C={comment_score} D={candidate['description_score']} "
                      f"| {candidate['title'][:50]}")
            time.sleep(1)

        self._log("PHASE2", f"Approved {len(scored_candidates)} candidates after deep analysis", 95)

        if not scored_candidates:
            self._log("END", "NO HIGH-INTENSITY VIDEOS FOUND — insufficient quality in deep analysis", 100)
            return

        # === PHASE 3: Final Selection ===
        scored_candidates.sort(key=lambda x: x["video_score"], reverse=True)
        final_count = 0
        for candidate in scored_candidates[:max_results]:
            self._save_candidate(account, candidate)
            final_count += 1

        self._log("END", f"🎯 Added {final_count} HIGH-INTENSITY candidates for "
                        f"{account.get('name', 'Unknown')} (Niche: {niche})", 100)

    # ================================================================
    # MAIN DISCOVERY CYCLE
    # ================================================================
    def run_cycle(self, limit_per_niche=5, user_id=None):
        self._log("SYSTEM", f"🚀 Starting High-Intensity Discovery Cycle "
                           f"(Limit: {limit_per_niche}/niche, User: {user_id or 'All'})")
        self._log("SYSTEM", "Mode: QUALITY > SPEED | Config: DATA-DRIVEN from Supabase")

        # Pre-load global config (cached for the entire cycle)
        self._global_config = None  # Reset cache
        self._user_overrides = {}   # Reset user override cache
        self._load_global_config()

        accounts = self.fetch_accounts_from_supabase(user_id=user_id)
        if not accounts:
            self._log("SYSTEM", "No active accounts to scan.")
            return

        for acc_idx, acc in enumerate(accounts):
            self._log("SYSTEM", f"\n{'='*60}")
            self._log("SYSTEM", f"Account [{acc_idx+1}/{len(accounts)}]: {acc.get('name', 'Unknown')} "
                               f"| Niche: {acc.get('niche', 'Unknown')}")
            sc = acc.get("search_config", {}) or {}
            self._log("SYSTEM", f"Search Config: {len(sc.get('search_terms', []))} terms, "
                               f"{len(sc.get('search_formats', []))} formats")
            self._log("SYSTEM", f"{'='*60}")

            try:
                self.search_viral_content(acc, max_results=limit_per_niche)
            except Exception as e:
                self._log("ERROR", f"Account scan failed: {str(e)[:100]}")

        self._log("SYSTEM", f"🏁 Discovery Cycle Completed. Mode: HIGH-INTENSITY | Config: DATA-DRIVEN")


if __name__ == "__main__":
    limit = 5
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except:
            pass

    engine = ContentDiscoveryEngine()
    engine.run_cycle(limit_per_niche=limit)
