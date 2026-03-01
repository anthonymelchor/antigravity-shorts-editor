import os
import subprocess
import json
import time
import re
import requests
import logging
import yt_dlp
from faster_whisper import WhisperModel
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Debug: Verificar clave de Gemini
gemini_key = os.environ.get("GEMINI_API_KEY", "")
if gemini_key:
    print(f"[Debug] Gemini API Key cargada (termina en: ...{gemini_key[-4:]})")
else:
    print("[Debug] ADVERTENCIA: GEMINI_API_KEY no encontrada en el entorno.")

# Configuración de Logging
LOG_FILE = "pipeline.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler() # Mantiene la salida en consola
    ]
)
logger = logging.getLogger(__name__)

# Ensure FFmpeg is available in PATH
if os.name == "nt":
    ffmpeg_bin = r"C:\Users\MELCHOR\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
    if ffmpeg_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_bin + os.pathsep + os.environ.get("PATH", "")

def download_video(url, output_path):
    logger.info(f"Downloading video from {url}...")
    try:
        ydl_opts = {
            'format': 'bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[height<=1440]',
            'merge_output_format': 'mp4',
            'outtmpl': output_path,
            'overwrites': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        logger.info(f"Video downloaded to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to download video: {str(e)}")
        raise e

def transcribe_audio(video_path, model_size="base"):
    logger.info(f"Transcribing {video_path} using faster-whisper ({model_size} model)...")
    try:
        # Run on CPU with INT8 representation for lower memory usage.
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

        segments, info = model.transcribe(video_path, beam_size=1, word_timestamps=True, vad_filter=True)

        logger.info(f"Detected language '{info.language}' with probability {info.language_probability}")

        words = []
        segments_data = []
        full_text = ""
        for segment in segments:
            full_text += segment.text + " "
            seg_words = []
            for word in segment.words:
                w_obj = {
                    "word": word.word.strip(),
                    "start": word.start,
                    "end": word.end
                }
                words.append(w_obj)
                seg_words.append(w_obj)
            
            segments_data.append({
                "text": segment.text.strip(),
                "start": segment.start,
                "end": segment.end,
                "words": seg_words
            })
                
        return {
            "text": full_text.strip(),
            "words": words,
            "segments": segments_data
        }
    except Exception as e:
        logger.error(f"Failed to transcribe audio: {str(e)}")
        raise e

def search_pexels_videos(query):
    """Searches Pexels for a video based on query and returns the best URL."""
    logger.info(f"Searching Pexels for B-roll: {query}...")
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        logger.warning(f"[Pexels] No API Key found. Skipping B-roll search.")
        return None
        
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=1"
    headers = {"Authorization": api_key}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data.get("videos"):
            video = data["videos"][0]
            for f in video["video_files"]:
                if f["height"] >= 720:
                    logger.info(f"[Pexels] Found high-res clip: {f['link']}")
                    return f["link"]
            logger.info(f"[Pexels] Found clip: {video['video_files'][0]['link']}")
            return video["video_files"][0]["link"]
        logger.info(f"[Pexels] No videos found for query: {query}")
    except Exception as e:
        logger.error(f"[Pexels] Search failed: {str(e)}")
        
    return None

def translate_full_transcript_global(segments_data):
    """Translates the ENTIRE transcript using 'Anchor Segments' and overlapping context."""
    if not segments_data: return []
    
    logger.info(f"Performing GLOBAL translation for {len(segments_data)} segments...")
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    # 2,000 segments = ~2 hours of video. This is the optimal safety limit for Gemini 2.5/3 Flash output.
    BATCH_SIZE = 2000
    all_translated_words = []
    
    for i in range(0, len(segments_data), BATCH_SIZE):
        batch = segments_data[i : i + BATCH_SIZE]
        batch_texts = [s["text"] for s in batch]
        
        # Overlapping Context: Take up to 5 segments from previous batch for flow/tone consistency
        prev_context = []
        if i > 0:
            prev_context = [s["text"] for s in segments_data[max(0, i-5) : i]]
        
        prompt = f"""
        Act as a professional translator. Translate the following list of segments into Spanish.
        
        CONTEXT FROM PREVIOUS SEGMENTS (Do NOT translate these, just use for continuity):
        {json.dumps(prev_context)}
        
        SEGMENTS TO TRANSLATE NOW:
        {json.dumps(batch_texts)}
        
        INSTRUCTIONS:
        1. Maintain a professional, clean, and engaging tone.
        2. Ensure terminological consistency with the context provided.
        3. IMPORTANT: Return ONLY a raw JSON array of strings.
        4. The output array MUST have EXACTLY {len(batch_texts)} strings. Each string corresponds to one segment from 'SEGMENTS TO TRANSLATE NOW'.
        """
        
        translated_texts = []
        max_retries = 3
        current_delay = 1
        
        for attempt in range(max_retries):
            try:
                # Brief pause to avoid rate limits
                time.sleep(current_delay) 
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                translated_texts = json.loads(response.text)
                
                if len(translated_texts) >= len(batch):
                    break # Success
                else:
                    logger.warning(f"Batch {i} returned fewer translations than expected ({len(translated_texts)}/{len(batch)}). Retrying...")
                    time.sleep(current_delay)
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    logger.warning(f"Quota hit for batch {i}. Retry {attempt+1}/{max_retries} in {current_delay}s...")
                    time.sleep(current_delay * 2)
                    current_delay *= 2 # Exponential backoff
                else:
                    logger.error(f"Error in batch {i}: {e}")
                    break

        if translated_texts:
            if len(translated_texts) != len(batch):
                logger.warning(f"Translation count mismatch in batch! Expected {len(batch)}, got {len(translated_texts)}. Some segments might lose sync.")
            
            # Map back and INTERPOLATE words for each segment
            for idx, trans_text in enumerate(translated_texts):
                if idx >= len(batch): break # Security limit
                orig_seg = batch[idx]
                seg_start = orig_seg["start"]
                seg_end = orig_seg["end"]
                duration = seg_end - seg_start
                
                trans_words = trans_text.split()
                if not trans_words: 
                    # If empty translation, use original to avoid empty subtitles
                    trans_words = [w["word"] for w in orig_seg["words"]]
                
                # Distribute segment duration across translated words
                word_dur = duration / len(trans_words)
                for w_idx, w_text in enumerate(trans_words):
                    all_translated_words.append({
                        "word": w_text,
                        "start": seg_start + (w_idx * word_dur),
                        "end": seg_start + ((w_idx + 1) * word_dur)
                    })
        else:
            logger.error(f"Global translation batch failed at segment {i} after retries. Falling back to original.")
            for s in batch:
                all_translated_words.extend(s["words"])
                
    return all_translated_words

def analyze_with_gemini(transcript):
    print("Analyzing transcript with Gemini to find the most viral 60-second clip...")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
        
    client = genai.Client(api_key=api_key)

    prompt = f"""
    Act as a Senior Viral Behavioral Engineer and Video Editor (OpusClip/Hormozi style) specialized in 2026 engagement patterns.
    Identify the TOP 10 most viral independent segments (35-70s) from the transcript. 
    It is CRITICAL to prioritize segments that justify the user's time investment instantly.

    VIRAL PRINCIPLES (ECOSYSTEM 2026):
    1. PRIORITIZATION: Value 'Saves' (utility) and 'DM Shares' (relatability) over likes.
    2. THE 3 C's RULE:
       - INSTANT CONTEXT: User must understand the topic in <1.5s (Hook).
       - NARRATIVE CLOSURE: Mini-story arc (Conflict -> Revelation/Solution).
       - CHARGE: Must provoke a physiological reaction (Laughter, Awe, Indignation) or provide "Save-worthy" utility.
    3. SEARCH MARKERS (Where to cut):
       - "THE SHIFT": Inflection points where opinion changes or mistakes are revealed.
       - COUNTER-INTUITIVE DATA: Challenging the status-quo (e.g., "Why X is killing your Y").
       - BREAKTHROUGH STORYTELLING: Rapid struggle and success arcs.
       - SOUNDBITES: Rhythmic, memorable non-generic phrases.

    SCORING LOGIC (1-100):
    Calculate the score based on:
    - HOOK (30%): Is it impossible to ignore in <3s?
    - RELATABILITY (20%): Does it trigger the "It happens to me too" feeling?
    - SAVE VALUE (30%): Is it info they need to keep for later?
    - ORIGINALITY (20%): Is it a fresh angle or a copy?
    Return clips sorted from HIGHEST to LOWEST score.

    HIGH-END EDITING STRATEGY:
    - SOCIAL SEARCH TITLES: Titles in Spanish that answer specific user questions (e.g., "¿Cómo lograr X...?" instead of "Mi Video").
    - MICRO-MOVEMENTS: Use zooms/cuts every 2-3s to keep the optic nerve active.
    - EMOJIS: Use 4-7 icons strictly aligned with concept keywords.
      AVAILABLE KEYWORDS: 'money', 'cash', 'rich', 'idea', 'think', 'mind', 'warning', 'alert', 'danger', 'stop', 'no', 'error', 'wrong', 'check', 'yes', 'correct', 'ok', 'time', 'clock', 'fast', 'speed', 'heart', 'love', 'hot', 'rocket', 'growth', 'up', 'down', 'work', 'task', 'office', 'success', 'win', 'star', 'laugh', 'funny', 'lol', 'wow', 'shock', 'amazing', 'cool', 'look', 'eye', 'sad', 'bad', 'cry', 'phone', 'computer', 'tech', 'camera', 'video', 'mic', 'search', 'find', 'link', 'lock', 'shield', 'tool', 'fix', 'build', 'book', 'learn', 'write', 'news', 'mail', 'chat', 'home', 'world', 'travel', 'sun', 'moon', 'star_special', 'music', 'sound', 'gift', 'party', 'health'
    
    Output Format (JSON Array):
    {{
      "clips": [
        {{
          "id": 1,
          "title": "<Social Search Spanish Title>",
          "score": 0,
          "hook_score": "A+",
          "save_value": "High",
          "start": 0.0,
          "end": 0.0,
          "reasoning": "<Explanation in SPANISH using the 3 C's and viral markers found>",
          "edit_events": {{
              "zooms": [{{ "time": 0.0, "type": "in", "intensity": 0.5 }}],
              "icons": [{{ "time": 0.0, "keyword": "keyword", "layout": "center", "duration": 1.5 }}],
              "b_rolls": [{{ "time": 0.0, "query": "English Pexels Search", "duration": 3.0 }}]
          }}
        }}
      ]
    }}

    Transcript: 
    {json.dumps(transcript['words'][:1500])}
    """

    time.sleep(1)  # Brief pause to avoid 429 rate limit
    response = None
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        
        # Robust JSON cleaning: Gemini sometimes adds markdown or comments
        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"): raw_text = raw_text[4:]
        
        # Remove common "hallucinated" comments like (use '...')
        import re
        clean_text = re.sub(r'\s*\(use [^)]+\)', '', raw_text)
        
        result = json.loads(clean_text)
        if "clips" in result and len(result["clips"]) > 0:
            best_clip = result["clips"][0]
            logger.info(f"Gemini identified {len(result['clips'])} potential clips. Best starts at {best_clip.get('start')}s.")
        
        return result
    except Exception as e:
        err_msg = f"Failed to process Gemini response. Error: {str(e)}"
        if response and hasattr(response, 'text'):
            err_msg += f" | Raw response: {response.text[:500]}..."
        logger.exception(err_msg)
        raise e


def extract_frame(video_path, time_in_seconds, output_path):
    logger.info(f"Extracting frame at {time_in_seconds}s to {output_path}...")
    try:
        command = [
            "ffmpeg",
            "-ss", str(time_in_seconds),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            "-y",
            output_path
        ]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
    except Exception as e:
        logger.error(f"Failed to extract frame: {str(e)}")
        raise e

def detect_face_center_mediapipe(image_path):
    """Uses Google's MediaPipe Tasks API to detect faces — works in any lighting/angle."""
    try:
        import mediapipe as mp
        
        # Path to the model file (downloaded once, ~100KB)
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blaze_face_short_range.tflite")
        
        if not os.path.exists(model_path):
            print(f"  [MediaPipe] Model not found at {model_path}. Skipping.")
            return None
        
        BaseOptions = mp.tasks.BaseOptions
        FaceDetector = mp.tasks.vision.FaceDetector
        FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions
        
        options = FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            min_detection_confidence=0.3
        )
        
        with FaceDetector.create_from_options(options) as detector:
            mp_image = mp.Image.create_from_file(image_path)
            results = detector.detect(mp_image)
            
            if not results.detections:
                print(f"  [MediaPipe] No faces detected in {image_path}")
                return None
            
            # Find the detection with highest confidence
            best = max(results.detections, key=lambda d: d.categories[0].score)
            bbox = best.bounding_box
            
            # Calculate horizontal center (normalized 0.0-1.0)
            img_w = mp_image.width
            center_x = (bbox.origin_x + bbox.width / 2.0) / img_w
            confidence = best.categories[0].score
            
            print(f"  [MediaPipe] Face found in {image_path} at center_x={center_x:.3f} (confidence={confidence:.2f})")
            return center_x
            
    except Exception as e:
        print(f"  [MediaPipe] Error: {e}")
        return None


def analyze_framing_high_precision_local(video_path, start_time, end_time):
    """Refactored Scene-Based Framing for high precision and scalability using MediaPipe (LOCAL)."""
    logger.info("Starting Local HIGH-PRECISION Framing Analysis (MediaPipe)...")
    try:
        import cv2
        import mediapipe as mp
    except ImportError:
        return {"layout": "single", "center": 0.5, "framing_segments": [{"start": 0, "end": end_time - start_time, "center": 0.5, "layout": "single"}]}

    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "efficientdet_lite0.tflite")
    detector_options = mp.tasks.vision.ObjectDetectorOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
        score_threshold=0.3
    )
    
    face_model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blaze_face_short_range.tflite")
    face_options = mp.tasks.vision.FaceDetectorOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=face_model_path),
        min_detection_confidence=0.4
    )

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    
    total_frames = int((end_time - start_time) * fps)

    # --- PERFORMANCE OPTIMIZATION CONFIG ---
    # REVERT INSTRUCTIONS:
    # 🚨 To return to original high-precision (slower but processes every frame):
    # 1. Set FRAME_SKIP_RATE = 1
    # 2. Set INTERNAL_ANALYSIS_WIDTH = None
    
    # [FRAME_SKIP_RATE]
    # Analyzes 1 out of every N frames. Value of 5 = 5x speed boost in analysis.
    FRAME_SKIP_RATE = 5 
    
    # [INTERNAL_ANALYSIS_WIDTH]
    # Resizes the frame internally for AI processing (Human eye doesn't see this).
    # Since we use normalized coordinates (0.0 to 1.0), the center remains 
    # mathematically identical whether we analyze at 480px or 1080px.
    # Result: Massive CPU relief with zero quality loss in the final output.
    INTERNAL_ANALYSIS_WIDTH = 480 
    # ----------------------------------------

    segments = []
    last_hsv_hist = None
    
    # 1. FRAME-BY-FRAME SCENE DETECTION (Super Fast)
    logger.info(f"Scanning {total_frames} frames for hard cuts and analyzing actors (Skip: {FRAME_SKIP_RATE}, Resize: {INTERNAL_ANALYSIS_WIDTH})...")
    
    with mp.tasks.vision.ObjectDetector.create_from_options(detector_options) as detector, \
         mp.tasks.vision.FaceDetector.create_from_options(face_options) as face_detector:
        for frame_idx in range(0, total_frames, FRAME_SKIP_RATE):
            # Jump forward if skip is enabled
            if FRAME_SKIP_RATE > 1:
                cap.set(cv2.CAP_PROP_POS_FRAMES, (start_time * fps) + frame_idx)

            ret, frame = cap.read()
            if not ret: break
            
            # Histogram comparison
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [180, 256], [0, 180, 0, 256])
            cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
            
            is_hard_cut = False
            if last_hsv_hist is not None:
                correlation = cv2.compareHist(last_hsv_hist, hist, cv2.HISTCMP_CORREL)
                if correlation < 0.85: # Hard switch detected
                    is_hard_cut = True
            
            # Analyze ONLY if it's the first frame of a scene or we need a sample
            if frame_idx == 0 or is_hard_cut:
                if segments:
                    segments[-1]["end"] = frame_idx / fps
                
                # RUN AI ONLY HERE
                # Performance Patch: Downscale for AI detection
                analysis_frame = frame
                if INTERNAL_ANALYSIS_WIDTH and frame.shape[1] > INTERNAL_ANALYSIS_WIDTH:
                    scale = INTERNAL_ANALYSIS_WIDTH / frame.shape[1]
                    h_target = int(frame.shape[0] * scale)
                    analysis_frame = cv2.resize(frame, (INTERNAL_ANALYSIS_WIDTH, h_target))

                rgb_frame = cv2.cvtColor(analysis_frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                
                # Use frames shape for dimensions (Crucial for correct normalization)
                h_f, w_f = analysis_frame.shape[:2]
                
                # Run detectors
                person_results = detector.detect(mp_image)
                face_results = face_detector.detect(mp_image)
                
                people = [d for d in person_results.detections if d.categories[0].category_name == 'person']
                faces = face_results.detections
                
                layout = "single"
                center = 0.5
                center_top = 0.5
                center_bottom = 0.5

                # --- NEW REFINED LOGIC (Cross-Validation) ---
                if len(people) >= 2:
                    layout = "split"
                    p_sorted = sorted(people, key=lambda d: d.bounding_box.origin_x)
                    p1_x = (p_sorted[0].bounding_box.origin_x + p_sorted[0].bounding_box.width/2) / w_f
                    p2_x = (p_sorted[1].bounding_box.origin_x + p_sorted[1].bounding_box.width/2) / w_f
                    center_top = p1_x
                    center_bottom = p2_x
                    center = p1_x
                elif len(people) == 1:
                    layout = "single"
                    p_center = (people[0].bounding_box.origin_x + people[0].bounding_box.width/2) / w_f
                    if len(faces) >= 1:
                        face_best = min(faces, key=lambda f: abs(((f.bounding_box.origin_x + f.bounding_box.width/2)/w_f) - p_center))
                        center = (face_best.bounding_box.origin_x + face_best.bounding_box.width/2) / w_f
                    else:
                        center = p_center
                elif len(faces) >= 1:
                    if len(faces) >= 2:
                        layout = "split"
                        f_sorted = sorted(faces, key=lambda f: f.bounding_box.origin_x)
                        center_top = (f_sorted[0].bounding_box.origin_x + f_sorted[0].bounding_box.width/2) / w_f
                        center_bottom = (f_sorted[1].bounding_box.origin_x + f_sorted[1].bounding_box.width/2) / w_f
                        center = center_top
                    else:
                        center = (faces[0].bounding_box.origin_x + faces[0].bounding_box.width/2) / w_f

                segments.append({
                    "start": frame_idx / fps,
                    "end": (frame_idx + FRAME_SKIP_RATE) / fps,
                    "layout": layout,
                    "center": center,
                    "center_top": center_top,
                    "center_bottom": center_bottom
                })
                
                if is_hard_cut:
                    logger.info(f"  [Cut] Detected at {(start_time + frame_idx/fps):.3f}s. Layout: {layout} | Center: {center:.2f}")

            else:
                # Just extend current segment
                segments[-1]["end"] = (frame_idx + FRAME_SKIP_RATE) / fps
                
            last_hsv_hist = hist

    cap.release()
    
    if not segments:
        segments.append({"start": 0.0, "end": end_time - start_time, "center": 0.5, "layout": "single"})
    else:
        # --- SMART SEGMENT MERGING (PRO VERSION) ---
        # Reduce timeline noise by merging visually similar segments
        merged = []
        if segments:
            current = segments[0]
            for i in range(1, len(segments)):
                next_seg = segments[i]
                
                # Conditions for merging:
                # 1. Same layout (single == single)
                # 2. Similar centering (less than 10% difference)
                layout_same = next_seg["layout"] == current["layout"]
                center_similar = abs(next_seg["center"] - current["center"]) < 0.10
                
                # If it's a split, check both centers
                if current["layout"] == "split":
                    ct_same = abs(next_seg["center_top"] - current["center_top"]) < 0.10
                    cb_same = abs(next_seg["center_bottom"] - current["center_bottom"]) < 0.10
                    center_similar = ct_same and cb_same

                if layout_same and center_similar:
                    # Extend current segment instead of creating a new one
                    current["end"] = next_seg["end"]
                else:
                    merged.append(current)
                    current = next_seg
            merged.append(current)
            segments = merged
    
    logger.info(f"High-Precision Analysis Complete. Identified {len(segments)} clean segments after merging.")
    return {
        "layout": segments[0]["layout"], 
        "center": segments[0]["center"], 
        "center_top": segments[0].get("center_top", 0.5),
        "center_bottom": segments[0].get("center_bottom", 0.5),
        "framing_segments": segments,
        "reasoning": f"Scene-First Framer ({len(segments)} cuts found)"
    }

def analyze_framing_multimodal_vision_gemini(video_path, start_time, end_time):
    logger.info("Extracting low-res video proxy for Gemini Multimodal Vision analysis (ASD)...")
    proxy_path = "framing_proxy.mp4"
    duration = end_time - start_time
    
    # Extract a low-res, low-bitrate proxy of the clip for Gemini to analyze
    command = [
        "ffmpeg",
        "-ss", str(start_time),
        "-t", str(duration),
        "-i", video_path,
        "-vf", "scale=-2:480",
        "-c:v", "libx264",
        "-crf", "28",
        "-preset", "veryfast",
        "-y",
        proxy_path
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Priority: Gemini Multimodal Video Analysis
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    logger.info(f"Uploading video proxy to Gemini for ASD analysis...")
    try:
        video_file = client.files.upload(file=proxy_path)
        
        while video_file.state.name == "PROCESSING":
            time.sleep(2)
            video_file = client.files.get(name=video_file.name)

        prompt = """
        Analyze this video clip as a professional video editor (style OpusClip).
        Your goal is to determine the best framing for a vertical (9:16) crop.
        
        CRITICAL INSTRUCTIONS:
        1. ACTIVE SPEAKER DETECTION (ASD): Analyze lip movement and audio sync throughout the clip. Identify who is speaking.
        2. IGNORE STATIC ELEMENTS: Ignore logos and background decorations.
        3. ANTI-WALL LOGIC: If people are at the sides and the center is empty, DO NOT frame the center. Focus ONLY on the humans.
        
        DECIDE LAYOUT:
        - "single": Use if one person talks most of the time.
        - "split": Use if there is a clear interaction between two people.
        
        Return ONLY raw JSON:
        {
            "layout": "single" | "split",
            "center": <float>,
            "center_top": <float>,
            "center_bottom": <float>,
            "reasoning": "Explain who is speaking and why you chose this"
        }
        """
        
        time.sleep(10) # Pause to avoid rate limit
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=[video_file, prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        
        # Cleanup
        try:
            client.files.delete(name=video_file.name)
        except:
            pass
        if os.path.exists(proxy_path):
            os.remove(proxy_path)
            
        result = json.loads(response.text)
        logger.info(f"Gemini layout decision: {result['layout']}")
        logger.info(f"Reasoning: {result.get('reasoning', 'N/A')}")
        return result

    except Exception as e:
        logger.exception(f"Gemini Vision framing failed. Error: {str(e)}")
        # Final cleanup attempt
        if os.path.exists(proxy_path):
            os.remove(proxy_path)
        return {"layout": "single", "center": 0.5, "center_top": 0.5, "center_bottom": 0.5, "reasoning": "AI Framing failed (Quota/429), using default centering."}

def process_video_ffmpeg(input_path, output_path, start_time, end_time, audio_path=None):
    logger.info(f"Extracting LOSSLESS clip: {start_time}s to {end_time}s...")
    try:
        duration = float(end_time) - float(start_time)
        
        command = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-i", input_path,
            "-t", str(duration),
            "-c:v", "libx264",
            "-crf", "17", # HIGH QUALITY (Visually Lossless)
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            output_path
        ]
        
        subprocess.run(command, check=True)
        logger.info(f"Lossless clip saved to {output_path}")

        # Extract precise WAV audio to guarantee 0 audio stutters in Chromium/Remotion
        audio_output = audio_path if audio_path else output_path.replace(".mp4", ".wav")
        logger.info(f"Extracting pristine Audio WAV track to {audio_output}...")
        audio_cmd = [
            "ffmpeg",
            "-y",
            "-i", output_path,
            "-vn",
            "-c:a", "pcm_s16le",
            "-ar", "44100",
            "-ac", "2",
            audio_output
        ]
        subprocess.run(audio_cmd, check=True)
        return output_path
    except Exception as e:
        logger.error(f"FFmpeg processing failed: {str(e)}")
        raise e


def slugify(text, max_length=60):
    """Convert text to a clean folder name."""
    import unicodedata
    if not text:
        return "untitled"
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    text = text.strip('_')
    text = re.sub(r'_+', '_', text)
    if len(text) > max_length:
        text = text[:max_length].rsplit('_', 1)[0]
    return text or "untitled"

if __name__ == "__main__":
    import sys
    import traceback
    import argparse

    # 0. Set up Argument Parser for World-Class Flexibility
    parser = argparse.ArgumentParser(description="RocotoClip High-Precision Backend Pipeline")
    parser.add_argument("--url", help="YouTube URL to process")
    parser.add_argument("--version", help="Version identifier (timestamp)")
    parser.add_argument("--user_id", help="User ID owner of this process")
    parser.add_argument("--title", help="Video title for folder naming")
    
    args = parser.parse_known_args()[0]
    
    youtube_url = args.url
    version = args.version or str(int(time.time()))
    user_id = args.user_id
    title = args.title

    # Define project directory structure with readable folder name
    folder_name = f"{slugify(title)}_{version}" if title else version
    PROJECT_DIR = os.path.join(os.getcwd(), "projects", folder_name)
    CLIPS_DIR = os.path.join(PROJECT_DIR, "clips")
    RENDERS_DIR = os.path.join(PROJECT_DIR, "renders")
    os.makedirs(CLIPS_DIR, exist_ok=True)
    os.makedirs(RENDERS_DIR, exist_ok=True)
    
    # Define working filenames for this run (organized in project folder)
    INPUT_FILE = os.path.join(PROJECT_DIR, "input.mp4")
    VIDEO_OUT = os.path.join(PROJECT_DIR, f"video_{version}.mp4")  # legacy, not directly used
    AUDIO_OUT = os.path.join(PROJECT_DIR, f"audio_{version}.wav")   # legacy, not directly used
    TRANSCRIPT_FILE = os.path.join(PROJECT_DIR, "transcript.json")

    try:
        # 1. Download (Always download if URL provided)
        if youtube_url:
            video_file = download_video(youtube_url, INPUT_FILE)
        elif os.path.exists("input_full.mp4"):
            video_file = "input_full.mp4"
            print("Using legacy input_full.mp4")
        else:
            # Fallback default
            youtube_url = "https://www.youtube.com/watch?v=okL1xL_hHOw"
            video_file = download_video(youtube_url, INPUT_FILE)
        
        # 1.5 Create lightweight proxy for framing analysis (ONE time)
        PROXY_FILE = os.path.join(PROJECT_DIR, "proxy.mp4")
        logger.info(f"Creating 480p proxy for framing analysis...")
        proxy_cmd = [
            "ffmpeg", "-y", "-i", video_file,
            "-vf", "scale=-2:480",
            "-c:v", "libx264", "-crf", "28", "-preset", "veryfast",
            "-an",  # No audio needed for visual analysis
            PROXY_FILE
        ]
        subprocess.run(proxy_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"Proxy created: {PROXY_FILE}")
        
        # 2. Transcribe
        transcript = transcribe_audio(video_file)
            
        # 2.5 GLOBAL TRANSLATION (Scaling improvement)
        full_translated_words = translate_full_transcript_global(transcript['segments'])

        # 3. Analyze
        multi_analysis = analyze_with_gemini(transcript)
        if not multi_analysis or "clips" not in multi_analysis or not multi_analysis["clips"]:
            raise ValueError("Gemini failed to identify any viral clips.")
            
        raw_clips = multi_analysis["clips"]
        # Sort by score desc just in case Gemini didn't
        raw_clips.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # Limit to 10
        raw_clips = raw_clips[:10]
        
        processed_clips = []
        
        for idx, analysis in enumerate(raw_clips):
            logger.info(f"--- Processing Clip #{idx+1} (Score: {analysis.get('score')}) ---")
            
            # Clip-specific filenames
            clip_id = idx + 1
            V_OUT = os.path.join(CLIPS_DIR, f"video_{version}_clip_{clip_id}.mp4")
            A_OUT = os.path.join(CLIPS_DIR, f"audio_{version}_clip_{clip_id}.wav")
            
            # 3.5 Adjust Transcript Timestamps
            start_time = float(analysis.get('start', 0.0))
            end_time = float(analysis.get('end', start_time + 30.0))
            
            adjusted_words = []
            for w in transcript['words']:
                if w['end'] > start_time and w['start'] < end_time:
                    adjusted_words.append({
                        "word": w['word'],
                        "start": max(0.0, w['start'] - start_time),
                        "end": w['end'] - start_time
                    })
            
            # 3.7 Extract Spanish Translation from Global Pool (CLONE to avoid shared mutation)
            translated_words = [
                {**w, "start": max(0.0, w["start"] - start_time), "end": w["end"] - start_time} 
                for w in full_translated_words 
                if w['end'] > start_time and w['start'] < end_time
            ]
            
            # 3.8 Intelligent Framing (uses lightweight proxy for speed, same normalized coords)
            framing_data = analyze_framing_high_precision_local(PROXY_FILE, start_time, end_time)
            
            # 3.85 Process B-roll Suggestions and Adjust Times
            edit_events = analysis.get("edit_events", {"zooms": [], "icons": [], "b_rolls": [], "backgrounds": []})
            for key, event_list in edit_events.items():
                if isinstance(event_list, list):
                    for event in event_list:
                        if 'time' in event:
                            event['time'] = max(0.0, float(event['time']) - start_time)

            # 3.9 Store complete data for this clip
            clip_data = {
                **analysis,
                "duration": end_time - start_time,
                "words": adjusted_words,
                "words_es": translated_words,
                "layout": framing_data.get("layout", "single"),
                "center": framing_data.get("center", 0.5),
                "center_top": framing_data.get("center_top", 0.5),
                "center_bottom": framing_data.get("center_bottom", 0.5),
                "framing_reasoning": framing_data.get("reasoning", ""),
                "framing_segments": framing_data.get("framing_segments", []),
                "edit_events": edit_events,
                "video_url": os.path.basename(V_OUT),
                "audio_url": os.path.basename(A_OUT)
            }
            
            # 4. Crop and Cut the physical clip
            process_video_ffmpeg(video_file, V_OUT, start_time, end_time, A_OUT)
            
            processed_clips.append(clip_data)

        # Fetch the original video title for the manifest
        video_title = "Unknown Video"
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                video_title = info.get('title', "Project")
        except: pass

        final_data = {
            "clips": processed_clips,
            "version": version,
            "user_id": user_id,
            "video_title": video_title,
            # For backward compatibility, keep top clip markers at root
            "words": processed_clips[0]["words"],
            "words_es": processed_clips[0]["words_es"],
            "video_url": processed_clips[0]["video_url"],
            "audio_url": processed_clips[0]["audio_url"]
        }
        
        with open(TRANSCRIPT_FILE, "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        
        # SECURITY: Removed global transcript_data.json write.
        # Each user's data stays isolated in transcript_{version}.json only.

        logger.info(f"Backend processing pipeline complete! Version: {version} (Generated {len(processed_clips)} clips)")
        # Force flush log
        for l in logger.handlers:
            l.flush()

    except Exception as e:
        logger.error("CRITICAL ERROR: Pipeline failed dramatically.")
        logger.error(traceback.format_exc())
        sys.exit(1)
