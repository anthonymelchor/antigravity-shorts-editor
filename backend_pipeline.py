import os
import subprocess
import json
import time
import requests
import logging
import yt_dlp
from faster_whisper import WhisperModel
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

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

# Ensure FFmpeg is available in PATH for the entire script (including yt-dlp)
ffmpeg_bin = r"C:\Users\MELCHOR\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
if ffmpeg_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] = ffmpeg_bin + os.pathsep + os.environ.get("PATH", "")

def download_video(url, output_path="temp_video.mp4"):
    print(f"Downloading video from {url}...")
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        # 'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    print(f"Video downloaded to {output_path}")
    return output_path

def transcribe_audio(video_path, model_size="base"):
    print(f"Transcribing {video_path} using faster-whisper ({model_size} model)...")
    # Run on CPU with INT8 representation for lower memory usage.
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    segments, info = model.transcribe(video_path, beam_size=5, word_timestamps=True)

    print(f"Detected language '{info.language}' with probability {info.language_probability}")

    words = []
    full_text = ""
    for segment in segments:
        full_text += segment.text + " "
        for word in segment.words:
            words.append({
                "word": word.word.strip(),
                "start": word.start,
                "end": word.end
            })
            
    return {
        "text": full_text.strip(),
        "words": words
    }

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

def analyze_with_gemini(transcript):
    print("Analyzing transcript with Gemini to find the most viral 60-second clip...")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
        
    client = genai.Client(api_key=api_key)

    prompt = f"""
    Act as a Senior Viral Video Editor (OpusClip/Hormozi style) with a HIGH-END, CLEAN aesthetic.
    Analyze the transcript and identify the most engaging, viral continuous segment (25-60s).
    
    CLEAN PROFESSIONAL EDITING STRATEGY (CRITICAL):
    1. DYNAMIC CUTS (Punch Zooms): Use "in" (fast scale jump) sparingly on important punchlines, and "out" to reset. Use a maximum of 2-5 zooms in the ENTIRE clip. Let the content breathe.
    2. DEPTH & MOVEMENT: Use "ken-burns" during storytelling segments for an extremely subtle, slow drift. NEVER USE "shake" or fast continuous movements.
    3. ICONS: Use them to reinforce keywords. Use a tasteful amount (e.g., 4-7 icons in the clip). Try "center" or "top" layouts. Ensure they pop cleanly.
    4. B-ROLL: Prioritize finding high-quality short b-roll clips from Pexels for context. Never use "shake".

    Output the result as raw JSON:

    {{
        "start": <float>,
        "end": <float>,
        "reasoning": "<why this will go viral>",
        "clip_text": "<text summary>",
        "edit_events": {{
            "zooms": [
                {{ "time": <float>, "type": "in" | "out" | "ken-burns", "intensity": 0.5 }}
            ],
            "icons": [
                {{ "time": <float>, "keyword": "money" | "idea" | "warning" | "time" | "heart" | "rocket" | "work" | "success", "layout": "center" | "top" | "grid" | "scattered", "duration": 1.5 }}
            ],
            "b_rolls": [
                {{ "time": <float>, "query": "<search_query>", "duration": 3.0 }}
            ]
        }}
    }}
    
    Transcript: 
    {json.dumps(transcript['words'][:1500])}
    """

    time.sleep(5)  # Pause to avoid 429 rate limit
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        
        result = json.loads(response.text)
        logger.info(f"Gemini identified clip from {result['start']}s to {result['end']}s.")
        logger.info(f"Reasoning: {result['reasoning']}")
        return result
    except Exception as e:
        logger.exception(f"Failed to process Gemini response. Response text: {getattr(response, 'text', 'N/A')}")
        raise e

def extract_frame(video_path, time_in_seconds, output_path):
    print(f"Extracting frame at {time_in_seconds}s to {output_path}...")
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


def analyze_framing_with_gemini(video_path, start_time, end_time):
    logger.info("Extracting low-res video proxy for multimodal framing analysis (ASD)...")
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
            model='gemini-2.0-flash', 
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
        return {"layout": "single", "center": 0.5}

def process_video_ffmpeg(input_path, output_path, start_time, end_time):
    print(f"Processing video with FFmpeg: extracting clip from {start_time}s to {end_time}s...")
    duration = float(end_time) - float(start_time)
    
    command = [
        "ffmpeg",
        "-y",
        "-ss", str(start_time),
        "-i", input_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        output_path
    ]
    
    subprocess.run(command, check=True)
    print(f"Processed video (raw clip) saved to {output_path}")
    return output_path

if __name__ == "__main__":
    import sys
    # Use URL from argument if provided, otherwise use default
    youtube_url = sys.argv[1] if len(sys.argv) > 1 else None
    
    try:
        # 0. Clean up previous runs to ensure we don't reuse old video metadata
        if os.path.exists("transcript_data.json"):
            os.remove("transcript_data.json")

        # 1. Download (Skip if already exists and no URL provided)
        if not os.path.exists("input_full.mp4") or youtube_url:
            if not youtube_url:
                youtube_url = "https://www.youtube.com/watch?v=okL1xL_hHOw"
            video_file = download_video(youtube_url, "input_full.mp4")
        else:
            video_file = "input_full.mp4"
            print("Using existing input_full.mp4")
        
        # 2. Transcribe
        transcript = transcribe_audio(video_file)
            
        # 3. Analyze
        # Make sure GEMINI_API_KEY is an environment variable!
        analysis = analyze_with_gemini(transcript)
        
        # 3.5 Adjust Transcript Timestamps
        # The cut video starts at 0s, so we must subtract analysis['start'] from all words
        start_time = float(analysis['start'])
        end_time = float(analysis['end'])
        
        adjusted_words = []
        for w in transcript['words']:
            if w['end'] > start_time and w['start'] < end_time:
                adjusted_words.append({
                    "word": w['word'],
                    "start": max(0.0, w['start'] - start_time),
                    "end": w['end'] - start_time
                })
                
        adjusted_transcript = {
            "text": analysis.get("clip_text", ""),
            "words": adjusted_words
        }
        
        # 3.8 Intelligent Framing (Gemini Vision)
        framing_data = analyze_framing_with_gemini(video_file, start_time, end_time)
        
        # 3.85 Process B-roll Suggestions and Adjust Times
        edit_events = analysis.get("edit_events", {"zooms": [], "icons": [], "b_rolls": [], "backgrounds": []})
        
        # Adjust timestamps for edit events relative to clip start
        for key, event_list in edit_events.items():
            if isinstance(event_list, list):
                for event in event_list:
                    if 'time' in event:
                        event['time'] = max(0.0, float(event['time']) - start_time)

        for broll in edit_events.get("b_rolls", []):
            query = broll.get("query")
            if query:
                print(f">>> Searching B-roll for: {query}...")
                url = search_pexels_videos(query)
                if url:
                    broll["url"] = url
                    print(f"  [Pexels] Found: {url}")

        # 3.9 Prepare final transcript data for Remotion
        final_data = {
            "text": analysis.get("clip_text", ""),
            "words": adjusted_words,
            "layout": framing_data.get("layout", "single"),
            "center": framing_data.get("center", 0.5),
            "center_top": framing_data.get("center_top", 0.5),
            "center_bottom": framing_data.get("center_bottom", 0.5),
            "framing_reasoning": framing_data.get("reasoning", ""),
            "edit_events": edit_events
        }
        
        with open("transcript_data.json", "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)

        # 4. Crop and Cut
        # We produce a wide clip (raw clip) and let Remotion handle the cropping.
        process_video_ffmpeg("input_full.mp4", "output_vertical_clip.mp4", start_time, end_time)
        
        print("Backend processing pipeline complete! Next step: Remotion for layout.")

        
    except Exception as e:
        print(f"Pipeline failed: {str(e)}")
        sys.exit(1)
