import os
import subprocess
import json
import time
import re
import requests
import logging
import yt_dlp
import numpy as np
import cv2
import mediapipe as mp
from faster_whisper import WhisperModel
from google import genai
from google.genai import types
from google.genai import types
import sys
import traceback
from dotenv import load_dotenv
import audio_processor

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
    # Windows-only: add local WinGet FFmpeg to PATH if ffmpeg isn't already accessible
    import shutil as _shutil
    if not _shutil.which("ffmpeg"):
        _ffmpeg_bin = r"C:\Users\MELCHOR\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
        if os.path.isdir(_ffmpeg_bin):
            os.environ["PATH"] = _ffmpeg_bin + os.pathsep + os.environ.get("PATH", "")
# On Linux/Ubuntu: ffmpeg is expected to be installed system-wide (apt install ffmpeg)


def download_video(url, output_path):
    """Downloads video and returns (file_path, video_title) tuple."""
    logger.info(f"Downloading video from {url}...")
    try:
        video_title = None
        ydl_opts = {
            'format': 'bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[height<=1440]',
            'merge_output_format': 'mp4',
            'outtmpl': output_path,
            'overwrites': True,
        }
        
        # Anti-bot server protection: use cookies if provided
        if os.path.exists("cookies.txt"):
            ydl_opts['cookiefile'] = "cookies.txt"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title') if info else None
        logger.info(f"Video downloaded to {output_path} | Title: {video_title or 'Unknown'}")
        return output_path, video_title
    except Exception as e:
        logger.error(f"Failed to download video: {str(e)}")
        raise e

def extract_audio(video_path, output_audio_path=None, format="wav", bitrate="32k"):
    """Extracts audio from video to a temporary WAV or MP3 file."""
    if output_audio_path is None:
        ext = "wav" if format == "wav" else "mp3"
        output_audio_path = video_path.rsplit('.', 1)[0] + f"_temp_audio.{ext}"
    
    logger.info(f"Extracting audio ({format}@{bitrate}): {output_audio_path}...")
    try:
        if format == "wav":
            command = [
                "ffmpeg", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                "-y", output_audio_path
            ]
        else: # mp3
            command = [
                "ffmpeg", "-i", video_path,
                "-vn", "-acodec", "libmp3lame", "-b:a", bitrate, "-ar", "16000", "-ac", "1",
                "-y", output_audio_path
            ]
            
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_audio_path
    except Exception as e:
        logger.error(f"Failed to extract audio: {str(e)}")
        return None


def transcribe_audio_local(video_path, model_size="base", model=None):
    """
    Local Whisper transcription.
    - model_size: 'base' (default, recommended) or 'tiny' (faster) / 'small'/'medium' (more accurate).
    - model: pass a pre-loaded WhisperModel instance to avoid reloading on every call.
    """
    logger.info(f"Transcribing {video_path} locally (Whisper {model_size})...")
    from faster_whisper import WhisperModel
    if model is None:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(video_path, beam_size=1, word_timestamps=True, vad_filter=True)
    
    words = []
    segments_data = []
    full_text = ""
    for segment in segments:
        full_text += segment.text + " "
        seg_words = []
        for word in segment.words:
            w_obj = {"word": word.word.strip(), "start": word.start, "end": word.end}
            words.append(w_obj)
            seg_words.append(w_obj)
        segments_data.append({"text": segment.text.strip(), "start": segment.start, "end": segment.end, "words": seg_words})
                
    return {"text": full_text.strip(), "words": words, "segments": segments_data, "language": info.language}

def transcribe_audio(video_path, model_size="base"):
    """
    Transcripción MULTIMODAL optimizada (Picard + Official Google Docs).
    Usa Gemini 3.1 Flash-Lite con esquema de respuesta estricto y resolución baja.
    """
    logger.info(f"=== INICIANDO TRANSCRIPCIÓN MULTIMODAL GEMINI (Fallback a Whisper) ===")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY no configurada.")
        
    client = genai.Client(api_key=api_key)
    
    try:
        # 1. Siempre extraer audio para mayor eficiencia (Gemini y Whisper local lo prefieren)
        logger.info(f"Extrayendo audio comprimido para transcripción...")
        # 48k es ideal para voz: muy ligero y con calidad suficiente para transcripción.
        target_upload = extract_audio(video_path, format="mp3", bitrate="48k")
        if not target_upload: 
            logger.warning("Fallo al extraer audio. Usando video original (Lento)...")
            target_upload = video_path

        logger.info(f"Subiendo archivo a Gemini... {os.path.basename(target_upload)}")
        file_obj = client.files.upload(file=target_upload)
        
        # Espera activa del procesamiento
        while file_obj.state == "PROCESSING":
            time.sleep(5)
            file_obj = client.files.get(name=file_obj.name)
            
        if file_obj.state == "FAILED":
            raise RuntimeError(f"Fallo en carga de archivo: {file_obj.error}")

        # 2. Definición del Esquema (Siguiendo la documentación oficial)
        response_schema = types.Schema(
            type=types.Type.OBJECT,
            required=["segments"],
            properties={
                "segments": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        required=["timestamp", "content", "voice_id"],
                        properties={
                            "timestamp": types.Schema(type=types.Type.STRING, description="Formato MM:SS"),
                            "content": types.Schema(type=types.Type.STRING, description="Texto íntegro hablado"),
                            "voice_id": types.Schema(type=types.Type.INTEGER, description="ID único para cada voz detectada"),
                            "speaker": types.Schema(type=types.Type.STRING, description="Nombre si aparece en pantalla"),
                        }
                    )
                )
            }
        )

        prompt = """
        Actúa como un experto traductor y transcriptor multimodal.
        1. IDIOMA: Si el audio es en INGLÉS, tradúcelo fielmente al ESPAÑOL. Si el audio ya es en ESPAÑOL, corrígelo ortográficamente pero mantén el contenido original.
        2. FIDELIDAD: Genera una transcripción íntegra (verbatim). NO resumas ni omitas partes. Mantén el tono y estilo del hablante.
        3. OCR: Usa la información visual (texto en pantalla) para identificar nombres de speakers si aparecen.
        4. DIARIZACIÓN: Asigna un 'voice_id' consistente (1, 2, 3...) a la misma persona en todo el video.
        5. TIMESTAMPS: Proporciona timestamps exactos por cada segmento en formato MM:SS.
        """
        logger.info(f"Solicitando generación de contenido a Gemini...")
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=[prompt, file_obj],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema
            )
        )
        
        # Limpieza (borrar archivo de la nube y local inmediatamente)
        client.files.delete(name=file_obj.name)
        if target_upload != video_path and os.path.exists(target_upload):
            os.remove(target_upload)

        if not response or not response.text:
            raise RuntimeError("Respuesta de Gemini vacía.")

        data = json.loads(response.text)
        segments_raw = data.get("segments", [])

        if not segments_raw:
            logger.warning("No se extrajeron segmentos de la respuesta de Gemini.")
            raise RuntimeError("Gemini no devolvió segmentos válidos.")

        # 3. Procesamiento y adaptación para el Pipeline (Word-level interpolation)
        words = []
        segments_data = []
        full_text = ""

        def ts_to_sec(ts):
            try:
                p = ts.split(':')
                if len(p) == 2: return int(p[0])*60 + float(p[1])
                if len(p) == 3: return int(p[0])*3600 + int(p[1])*60 + float(p[2])
            except: pass
            return 0.0

        for i, s in enumerate(segments_raw):
            start_s = ts_to_sec(s.get('timestamp', '00:00'))
            
            # Estimamos duración mirando el siguiente segmento
            if i < len(segments_raw) - 1:
                end_s = ts_to_sec(segments_raw[i+1].get('timestamp', '00:00'))
            else:
                end_s = start_s + 5.0 # Margen final si es el último
                
            text = s.get('content', '').strip()
            if not text: continue
            
            full_text += text + " "
            
            # Interpolación necesaria para el resto de herramientas de edición (zooms/icons)
            raw_words = text.split()
            seg_words = []
            if raw_words:
                dur = max(0.1, end_s - start_s)
                w_dur = dur / len(raw_words)
                for j, w in enumerate(raw_words):
                    w_obj = {
                        "word": w.strip(),
                        "start": start_s + (j * w_dur),
                        "end": start_s + ((j + 1) * w_dur)
                    }
                    words.append(w_obj)
                    seg_words.append(w_obj)
            
            segments_data.append({
                "text": text,
                "start": start_s,
                "end": end_s,
                "words": seg_words,
                "voice": s.get("voice_id", 0),
                "speaker": s.get("speaker", "Unknown")
            })

        logger.info(f"Transcripción finalizada: {len(segments_data)} segmentos procesados.")
        return {
            "text": full_text.strip(),
            "words": words,
            "segments": segments_data,
            "language": "es"
        }

    except Exception as e:
        logger.error(f"FALLO EN TRANSCRIPCIÓN GEMINI: {str(e)}")
        
        # ⚠️ NEW FALLBACK CHAIN: Gemini -> Local Whisper (CPU)
        logger.info("⚠️ Activando fallback directamente a Whisper Local (Lento pero seguro)...")
        try:
            # Extraer audio si no existe ya para Whisper (Whisper prefiere wav o mp3)
            audio_for_whisper = extract_audio(video_path, format="mp3", bitrate="64k")
            result = transcribe_audio_local(audio_for_whisper or video_path, model_size=model_size)
            
            # Limpiar audio temporal de whisper si se creó
            if audio_for_whisper and os.path.exists(audio_for_whisper):
                os.remove(audio_for_whisper)
                
            return result
        except Exception as local_e:
            logger.error(f"FALLO CRÍTICO EN WHISPER LOCAL: {str(local_e)}")
            raise local_e


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

def translate_full_transcript_global(segments_data, source_lang="en"):
    """Translates or refines the ENTIRE transcript using 'Anchor Segments' and overlapping context."""
    if not segments_data: return []
    
    logger.info(f"Performing GLOBAL transcript refinement/translation (Source: {source_lang})...")
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
        
        # Prepare a dictionary for translation to maintain mapping integrity
        batch_map = {str(idx): text for idx, text in enumerate(batch_texts)}
        
        prompt = f"""
        Act as a professional transcription refiner and translator. 
        Your goal is to provide a LITERAL version in Spanish of the provided segments.
        
        STRICT RULES:
        1. NO PARA-PHRASING. The text must match the phonetic audio as closely as possible.
        2. DO NOT "improve" or "clean up" the speaker's style. If the speaker is repetitive, keep it.
        3. DO NOT remove filler words.
        4. TECHNICAL TERMS: Ensure terms like 'ChatGPT', 'AI', 'SaaS', 'B-Roll', etc., are spelled correctly.
        5. LANGUAGE: If the input is English, translate it to Spanish. If the input is already Spanish, FIX ONLY spelling and punctuation.
        6. FIDELITY: Maintain the exact same amount of information. Your task is literal fidelity.
        
        CONTEXT FROM PREVIOUS SEGMENTS (Do NOT process these):
        {json.dumps(prev_context)}
        
        SEGMENTS TO PROCESS (Index mapping):
        {json.dumps(batch_map)}
        
        OUTPUT FORMAT (STRICT TEXT LABELS):
        Return EXACTLY the following structure for each processed segment. NO JSON. NO CODE FORMATTING.
        
        [SEGMENT_START]
        Index: <Index number here>
        Text: <Spanish translation here>
        [SEGMENT_END]
        """
        
        translated_map = {}
        max_retries = 3
        current_delay = 1
        
        for attempt in range(max_retries):
            try:
                time.sleep(current_delay) 
                response = client.models.generate_content(
                    model='gemini-3.1-flash-lite-preview',
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="text/plain")
                )
                raw_translation = response.text.strip()
                
                # --- PARSER BASADO EN REGEX ---
                translated_map = {}
                seg_blocks = re.findall(r'\[SEGMENT_START\](.*?)\[SEGMENT_END\]', raw_translation, re.DOTALL)
                
                for block in seg_blocks:
                    idx_match = re.search(r'Index:\s*(\d+)', block)
                    txt_match = re.search(r'Text:\s*(.*)', block, re.DOTALL)
                    if idx_match and txt_match:
                        idx_val = idx_match.group(1).strip()
                        txt_val = txt_match.group(1).strip()
                        translated_map[idx_val] = txt_val
                
                # Validate that we have most of the keys
                if len(translated_map) >= len(batch) * 0.8: # Tolerance: 80% successfully translated is enough to carry on
                    break # Success
                else:
                    logger.warning(f"Batch {i} returned fewer translations than expected ({len(translated_map)}/{len(batch)}). Retrying...")
                    time.sleep(current_delay)
            except Exception as e:
                # ... same error handling ...
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    logger.warning(f"Quota hit for batch {i}. Retry {attempt+1}/{max_retries} in {current_delay}s...")
                    time.sleep(current_delay * 2)
                    current_delay *= 2 
                else:
                    logger.error(f"Error in batch {i}: {e}")
                    break

        if translated_map:
            # Map back using the ORIGINAL order and segment boundaries
            for idx in range(len(batch)):
                idx_str = str(idx)
                trans_text = translated_map.get(idx_str)
                
                orig_seg = batch[idx]
                seg_start = orig_seg["start"]
                seg_end = orig_seg["end"]
                duration = seg_end - seg_start
                
                if not trans_text:
                    # Fallback if key is missing
                    trans_words = [w["word"] for w in orig_seg["words"]]
                else:
                    trans_words = trans_text.split()
                
                if not trans_words:
                    trans_words = ["[...]"]
                
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



def analyze_viral_clips_from_text(transcript_json, user_id=None, video_title="Unknown"):
    """
    MOTOR DE EXTRACCIÓN VIRAL v4.0 (TRANSCRIPT) - Gemini lee la transcripción de Whisper
    """
    logger.info("=== MOTOR DE EXTRACCIÓN VIRAL v4.0 (Text Transcript) ===")
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    # Preparar el texto para el prompt
    text_content = ""
    for seg in transcript_json.get("segments", []):
        text_content += f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}\n"

    prompt = f"""
Eres el mejor editor de contenido viral del mundo. Tu misión es LEER esta transcripción y extraer los mejores momentos para convertirlos en Shorts/Reels/TikToks.

TITULO DEL VIDEO (CONTEXTO): {video_title}

REGLAS DE ORO:
1. Encuentra momentos con HOOK fuerte, HOLD de retención y REWARD al final.
2. Cada clip DEBE durar entre 25 y 90 segundos. Si el momento es muy corto, incluye el contexto anterior (pregunta/introducción) o posterior. OBLIGATORIO.
3. Extrae TODOS los grandes momentos (hasta 15 si el video es rico en contenido).
4. Los Start y End deben ser precisos basados en los tiempos que ves en el texto.

TRANSCRIPCIÓN:
{text_content}

FORMATO DE RESPUESTA (ETIQUETAS ESTRICTAS):
Debes responder EXCLUSIVAMENTE con texto plano usando estas etiquetas:

[CONTEXT_START]
Tema Central: <resumen del video>
Es Podcast: <true/false>
Tono: <motivacional/polemico/etc>
[CONTEXT_END]

[CLIP_START]
Title: <Titulo viral llamativo>
Start: <tiempo en segundos, ej: 125.5>
End: <tiempo en segundos, ej: 185.0>
Score: <1 a 11>
Is Title Clip: <true/false>
Hook Type: <CONTRAINTUITIVO/DATO_IMPACTO/PREGUNTA_DOLOR/DIAGNOSTICO/LOOP_ABIERTO>
Reasoning: <por qué es viral>
Classification: <EXPLOSION/AUTORIDAD/CONVERSION>
[CLIP_END]

Responde ahora:
"""

    max_retries = 3
    for attempt in range(max_retries):
        logger.info(f"Pidiendo a Gemini que analice el texto (Intento {attempt + 1}/{max_retries})...")
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="text/plain"),
            )

            raw_text = response.text.strip()
            result = {"context": {}, "clips": []}
            
            context_match = re.search(r'\[CONTEXT_START\](.*?)\[CONTEXT_END\]', raw_text, re.DOTALL)
            if context_match:
                ctx_text = context_match.group(1)
                for line in ctx_text.split('\n'):
                    if 'Tema Central:' in line: result["context"]["tema_central"] = line.split(':', 1)[1].strip()
                    elif 'Es Podcast:' in line: result["context"]["is_podcast"] = 'true' in line.lower()
            
            clips_blocks = re.findall(r'\[CLIP_START\](.*?)\[CLIP_END\]', raw_text, re.DOTALL)
            for idx, c_text in enumerate(clips_blocks):
                clip_obj = {
                    "id": idx + 1,
                    "title": "", "start": 0.0, "end": 0.0, "score": 0, "is_title_clip": False,
                    "reasoning": "", "classification": [], "edit_events": {"zooms": [], "icons": [], "b_rolls": []}
                }
                for line in c_text.split('\n'):
                    line = line.strip()
                    if line.startswith('Title:'): clip_obj['title'] = line.replace('Title:', '').strip()
                    elif line.startswith('Start:'): clip_obj['start'] = float(re.findall(r'(\d+\.?\d*)', line)[0])
                    elif line.startswith('End:'): clip_obj['end'] = float(re.findall(r'(\d+\.?\d*)', line)[0])
                    elif line.startswith('Score:'): clip_obj['score'] = float(re.findall(r'(\d+\.?\d*)', line)[0])
                    elif line.startswith('Is Title Clip:'): clip_obj['is_title_clip'] = 'true' in line.lower()
                
                duration = clip_obj["end"] - clip_obj["start"]
                if clip_obj["score"] >= 5 and 25 <= duration <= 100:
                    result["clips"].append(clip_obj)
            
            return result

        except Exception as e:
            logger.error(f"Error en análisis de texto Gemini: {e}")
            if attempt == max_retries - 1: raise e
            time.sleep(2)
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
    """Uses Google MediaPipe Tasks API to detect faces - works in any lighting/angle."""
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


def _extract_split_candidates(people, faces, w_f):
    """
    Extrae los centros horizontales de los dos sujetos más prominentes
    si están suficientemente separados y en mitades opuestas.
    Devuelve (es_candidato_split, centro_izq, centro_der).
    """
    subjects = people if len(people) >= 2 else (faces if len(faces) >= 2 else [])
    if len(subjects) < 2:
        return False, 0.5, 0.5

    top2 = sorted(subjects,
                  key=lambda d: d.bounding_box.width * d.bounding_box.height,
                  reverse=True)[:2]

    centers = sorted(
        [(d.bounding_box.origin_x + d.bounding_box.width / 2) / w_f for d in top2]
    )
    c_left, c_right = centers[0], centers[1]

    # Separación mínima 25% — descarta abrazados, grupos compactos, multitudes
    if (c_right - c_left) < 0.25:
        return False, (c_left + c_right) / 2, (c_left + c_right) / 2

    # Cada sujeto debe estar en su propia mitad de pantalla
    if not (c_left < 0.55 and c_right > 0.45):
        return False, c_left, c_right

    return True, c_left, c_right




def analyze_framing_high_precision_local(video_path, start_time, end_time, is_podcast=True, detector=None, face_detector=None):
    """
    Motor de Framing Profesional (Shot-Based Decision).
    1. Detecta cortes de cámara exactos usando diferencias de luminancia (Matemática pura).
    2. Analiza un frame representativo por cada toma (escena) con IA.
    3. Bloquea el layout para toda la toma (Estabilidad total, cero parpadeo).
    """
    import mediapipe as mp
    from mediapipe.tasks.python import vision
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    
    # Manejo de detectores pre-cargados (Optimización de Flujo Invertido)
    _should_close = False
    if detector is None or face_detector is None:
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "efficientdet_lite0.tflite")
        face_model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blaze_face_short_range.tflite")
        
        det_options = vision.ObjectDetectorOptions(base_options=mp.tasks.BaseOptions(model_asset_path=model_path), score_threshold=0.3)
        face_options = vision.FaceDetectorOptions(base_options=mp.tasks.BaseOptions(model_asset_path=face_model_path), min_detection_confidence=0.4)
        
        detector = vision.ObjectDetector.create_from_options(det_options)
        face_detector = vision.FaceDetector.create_from_options(face_options)
        _should_close = True

    start_frame = int(start_time * fps)
    total_frames_to_read = int((end_time - start_time) * fps)
    
    # --- FASE 1: Detección Matemática de Cortes de Cámara ---
    # Escaneamos rápido buscando el frame EXACTO del cambio de plano.
    logger.info(f"Fase 1: Detectando cortes de cámara exactos en {total_frames_to_read} frames...")
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    
    cuts = [0] # Frame relativo al inicio del clip
    last_gray = None
    
    # Parámetros de sensibilidad para cortes
    CUT_SENSITIVITY = 0.15 # Más bajo = más sensible a cambios de cámara sutiles
    MIN_SCENE_FRAMES = int(fps * 0.5) # Mínimo 0.5s por toma para evitar parpadeo
    
    for i in range(total_frames_to_read):
        ret, frame = cap.read()
        if not ret: break
        
        # Convertir a escala de grises pequeña para comparar rápido
        small = cv2.resize(frame, (64, 36))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype('float32') / 255.0
        
        if last_gray is not None:
            # Diferencia absoluta media entre frames
            diff = float(np.abs(gray - last_gray).mean())
            if diff > CUT_SENSITIVITY:
                # Evitar cortes demasiado seguidos si no es necesario
                if len(cuts) == 0 or (i - cuts[-1]) > MIN_SCENE_FRAMES:
                    cuts.append(i) # Guardamos el frame exacto del corte
        
        last_gray = gray
    
    cuts.append(total_frames_to_read)
    logger.info(f"  Fase 1 completa: {len(cuts)-1} tomas detectadas.")

    # --- FASE 2: Análisis de IA por Toma (Lock-In) ---
    # Para cada toma, decidimos el layout basándonos en el frame central.
    logger.info("Fase 2: Aplicando decisiones por toma y analizando con IA...")
    final_segments = []
    
    for j in range(len(cuts) - 1):
        s_frame = cuts[j]
        e_frame = cuts[j+1]
        if (e_frame - s_frame) < 2: continue # Ignorar micro-escenas
        
        # Tomamos el frame central de esta toma para decidir el layout
        mid_frame = s_frame + (e_frame - s_frame) // 2
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame + mid_frame)
        ret, frame = cap.read()
        if not ret: continue
        
        # Análisis con MediaPipe
        h_f, w_f = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        p_res = detector.detect(mp_image)
        f_res = face_detector.detect(mp_image)
        
        people = [d for d in p_res.detections if d.categories[0].category_name == 'person']
        faces = f_res.detections
        
        layout = "single"
        center = 0.5
        center_top = 0.5
        center_bottom = 0.5
        
        # Lógica de decisión Profesional (Podcast-First)
        # Priorizamos caras si hay 2, o personas si hay 2.
        if len(people) >= 2 or (len(faces) >= 2 and is_podcast):
            layout = "split"
            actors = sorted(people if len(people) >= 2 else faces, key=lambda d: d.bounding_box.origin_x)
            center_top = (actors[0].bounding_box.origin_x + actors[0].bounding_box.width/2) / w_f
            center_bottom = (actors[-1].bounding_box.origin_x + actors[-1].bounding_box.width/2) / w_f
            center = center_top
        elif len(people) == 1 or len(faces) == 1:
            target = people[0] if len(people) == 1 else faces[0]
            center = (target.bounding_box.origin_x + target.bounding_box.width/2) / w_f
        
        # Asegurar límites
        center = max(0.1, min(0.9, center))
        center_top = max(0.1, min(0.9, center_top))
        center_bottom = max(0.1, min(0.9, center_bottom))
        
        # Creamos el segmento estable para TODA la toma
        final_segments.append({
            "start": s_frame / fps,
            "end": e_frame / fps,
            "layout": layout,
            "center": center,
            "center_top": center_top,
            "center_bottom": center_bottom
        })

    cap.release()
    if _should_close:
        detector.close()
        face_detector.close()
    
    # --- FASE 3: Limpieza y Retorno ---
    if not final_segments:
        final_segments.append({"start": 0.0, "end": end_time - start_time, "layout": "single", "center": 0.5})

    logger.info(f"Proceso completado. {len(final_segments)} segmentos estables generados.")
    return {
        "layout": final_segments[0]["layout"],
        "center": final_segments[0]["center"],
        "center_top": final_segments[0].get("center_top", 0.5),
        "center_bottom": final_segments[0].get("center_bottom", 0.5),
        "framing_segments": final_segments,
        "reasoning": f"Shot-Based Stabilization ({len(final_segments)} scenes)"
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
            model='gemini-3.1-flash-lite-preview', 
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
            "-g", "1", # CRITICAL FOR FRAME-ACCURATE SCRUBBING ON THE WEB
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


def snap_to_sentence_start(start_time, words, lookback_seconds=4.0):
    """
    Si el start_time cae en medio de una oración, retrocede al inicio
    de la frase más cercana dentro de una ventana de lookback_seconds.
    Detecta inicio de frase por dos señales:
      1. La palabra empieza con mayuscula (inicio de oracion)
      2. Hay una pausa larga antes de la palabra (>0.4 segundos entre palabras)
    Siempre retrocede al candidato mas reciente antes del start_time
    para no alargar el clip más de lo necesario.
    """
    window_start = max(0.0, start_time - lookback_seconds)
    candidates = [w for w in words if window_start <= w['start'] <= start_time]

    if not candidates:
        return start_time

    best_start = start_time
    for i, w in enumerate(candidates):
        # Señal 1: palabra empieza con mayúscula → inicio de oración
        if w['word'] and w['word'][0].isupper():
            best_start = w['start']
        # Señal 2: pausa larga antes de esta palabra → inicio de frase
        if i > 0:
            pause = w['start'] - candidates[i - 1]['end']
            if pause > 0.4:
                best_start = w['start']

    if best_start != start_time:
        logger.info(f"[Snap] Inicio ajustado: {start_time:.2f}s → {best_start:.2f}s")

    return best_start


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
    parser.add_argument("--niche", help="Specified niche for the project")
    parser.add_argument("--whisper_model", default="base",
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Whisper model size (default: base). Use 'tiny' for speed or 'small'/'medium' for higher accuracy.")
    parser.add_argument("--enable_bg_music", default="true",
                        help="Whether to mix background music with ducking (true/false, default: true)")
    
    args = parser.parse_known_args()[0]
    
    youtube_url = args.url
    version = args.version or str(int(time.time()))
    user_id = args.user_id
    title = args.title
    initial_niche = args.niche
    whisper_model_size = args.whisper_model  # 'tiny' by default
    enable_bg_music = args.enable_bg_music.lower() != 'false'  # True unless explicitly 'false'

    # Define project directory structure with readable folder name
    folder_name = f"{slugify(title)}_{version}" if title else version
    PROJECT_DIR = os.path.join(os.getcwd(), "projects", folder_name)
    CLIPS_DIR = os.path.join(PROJECT_DIR, "clips")
    RENDERS_DIR = os.path.join(PROJECT_DIR, "renders")
    os.makedirs(CLIPS_DIR, exist_ok=True)
    os.makedirs(RENDERS_DIR, exist_ok=True)
    
    # Define working filenames for this run (organized in project folder)
    INPUT_FILE = os.path.join(PROJECT_DIR, "input.mp4")
    TRANSCRIPT_FILE = os.path.join(PROJECT_DIR, "transcript.json")

    try:
        # --- START OF PIPELINE LOGGER BANNER ---
        logger.info("")
        logger.info("╔══════════════════════════════════════════════════════════════════════════╗")
        logger.info("║                    🚀 ANTIGRAVITY SHORTS PIPELINE v3.5                   ║")
        logger.info("╚══════════════════════════════════════════════════════════════════════════╝")
        logger.info(f"   🎥 VIDEO: {title or 'Unknown'}")
        logger.info(f"   🔗 LINK : {youtube_url or 'Local File'}")
        logger.info(f"   🆔 USER : {user_id}")
        logger.info(f"   🏷️ NICHE: {initial_niche or 'Generic'}")
        logger.info("   ──────────────────────────────────────────────────────────────────")
        logger.info("")

        global_start = time.time()

        # 1. Download (Always download if URL provided)
        t_start = time.time()
        
        # --- MODO TEST: Si la URL es la palabra 'test', usamos input.mp4 local ---
        if youtube_url and youtube_url.lower().strip() == "test":
            logger.info("🧪 [MODO TEST] Usando 'input.mp4' local de la raíz del proyecto.")
            if os.path.exists("input.mp4"):
                import shutil
                shutil.copy("input.mp4", INPUT_FILE)
                video_file = INPUT_FILE
                youtube_url = "Local Test File"
            else:
                logger.error("❌ MODO TEST: 'input.mp4' no encontrado en la raíz. Abortando.")
                raise FileNotFoundError("'input.mp4' missing for test mode.")
        elif youtube_url:
            video_file, fetched_title = download_video(youtube_url, INPUT_FILE)
            # Use title fetched during download — no second yt-dlp call needed
            if not title and fetched_title:
                title = fetched_title
        elif os.path.exists("input_full.mp4"):
            video_file = "input_full.mp4"
            print("Using legacy input_full.mp4")
        else:
            # Fallback default
            youtube_url = "https://www.youtube.com/watch?v=okL1xL_hHOw"
            video_file, fetched_title = download_video(youtube_url, INPUT_FILE)
            if not title and fetched_title:
                title = fetched_title
        # --- FIN MODO TEST ---
        logger.info(f"   ✅ [PHASE 1] Download completed in {time.time() - t_start:.2f}s")
        
        # 1.5 NOTE: No proxy needed — analyze_framing_high_precision_local already
        # downscales internally to INTERNAL_ANALYSIS_WIDTH (480px). Using a pre-scaled
        # proxy caused FPS mismatches and wrong frame timestamps vs the original file.
        # The validate_universal_fix.py approach (using the original video directly) is correct.
        logger.info(f"   ✅ [PHASE 1.5] Skipping proxy — framing will use original video directly (480px internal downscale)")
        
        # 2. Transcribe Full Audio with Whisper (Local) — model loaded ONCE and reused
        t_trans = time.time()
        FULL_AUDIO = os.path.join(PROJECT_DIR, "audio_for_whisper.mp3")
        extract_audio(video_file, FULL_AUDIO, format="mp3", bitrate="64k")
        
        logger.info(f"   🧠 Loading Whisper model '{whisper_model_size}' into memory (once)...")
        from faster_whisper import WhisperModel as _WhisperModel
        shared_whisper = _WhisperModel(whisper_model_size, device="cpu", compute_type="int8")
        
        full_transcript = transcribe_audio_local(FULL_AUDIO, model_size=whisper_model_size, model=shared_whisper)
        logger.info(f"   ✅ [PHASE 2] Full Transcription (Whisper '{whisper_model_size}') completed in {time.time() - t_trans:.2f}s")

        # 3. Analyze Transcript with Gemini 2.5 Flash
        # Title was already captured during download — no second yt-dlp call needed
        t_analysis = time.time()
        video_title_for_ai = title or "Unknown Video"

        analysis_result = analyze_viral_clips_from_text(full_transcript, user_id=user_id, video_title=video_title_for_ai)
        logger.info(f"   ✅ [PHASE 3] Gemini Viral Text Analysis completed in {time.time() - t_analysis:.2f}s")
        
        context = analysis_result.get("context", {})
        raw_clips = analysis_result.get("clips", [])
        is_podcast_global = context.get("is_podcast", False)
        logger.info(f"GEMINI CONTEXT — Theme: {context.get('tema_central', 'N/A')} | Format: {'Podcast' if is_podcast_global else 'Monologue'}")

        if not raw_clips:
            raise ValueError("Gemini failed to identify any viral clips from transcription.")
            
        # Cleanup analysis audio
        if os.path.exists(FULL_AUDIO): os.remove(FULL_AUDIO)

        # 4. Process Each Clip
        from mediapipe.tasks.python import vision
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "efficientdet_lite0.tflite")
        face_model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blaze_face_short_range.tflite")
        
        det_options = vision.ObjectDetectorOptions(base_options=mp.tasks.BaseOptions(model_asset_path=model_path), score_threshold=0.3)
        face_options = vision.FaceDetectorOptions(base_options=mp.tasks.BaseOptions(model_asset_path=face_model_path), min_detection_confidence=0.4)
        
        shared_detector = vision.ObjectDetector.create_from_options(det_options)
        shared_face_detector = vision.FaceDetector.create_from_options(face_options)

        processed_clips = []

        # ── BACKGROUND MUSIC SELECTION (once per run) ──────────────────────
        selected_music_path = None
        if enable_bg_music:
            MUSIC_BASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "remotion-app", "public", "music")
            selected_music_path = audio_processor.select_music_for_niche(initial_niche or "", MUSIC_BASE_PATH)
            if selected_music_path:
                logger.info(f"   🎵 Background music selected: {os.path.basename(selected_music_path)} (Niche: {initial_niche})")
            else:
                logger.info(f"   🔇 No background music found for niche '{initial_niche}'. Proceeding without BGM.")
        else:
            logger.info(f"   🔇 Background music DISABLED by user. Keeping clean audio.")
        # ───────────────────────────────────────────────────────────────────
        
        for idx, analysis in enumerate(raw_clips):
            logger.info(f"--- Processing Clip #{idx+1} (Score: {analysis.get('score')}) ---")
            
            clip_id = idx + 1
            V_OUT = os.path.join(CLIPS_DIR, f"video_{version}_clip_{clip_id}.mp4")
            A_OUT = os.path.join(CLIPS_DIR, f"audio_{version}_clip_{clip_id}.wav")
            
            start_time = float(analysis.get('start', 0.0))
            end_time = float(analysis.get('end', start_time + 30.0))
            
            # PHASE 3.5: Extract Clip first
            process_video_ffmpeg(video_file, V_OUT, start_time, end_time, A_OUT)

            # PHASE 3.55: Mix Background Music with Static Volume (if available)
            if selected_music_path:
                logger.info(f"      🎵 Mixing music '{os.path.basename(selected_music_path)}' with static background volume...")
                success = audio_processor.mix_audio_with_ducking(
                    voice_path=A_OUT,
                    music_path=selected_music_path,
                    output_path=A_OUT,
                    bg_volume=0.06
                )
                if success:
                    logger.info(f"      ✅ Music mix applied successfully")
                else:
                    logger.warning(f"      ⚠️ Music mixing failed, keeping original clean audio")

            # PHASE 3.6: Slice Global Transcription (Fast and DRY)
            t_slice = time.time()
            # Filter words from full_transcript that fall between start_time and end_time
            clip_words = []
            for w in full_transcript.get('words', []):
                if start_time <= w['start'] <= end_time:
                    # Adjust timestamp to be relative to clip start
                    new_w = w.copy()
                    new_w['start'] = max(0.0, float(w['start']) - start_time)
                    new_w['end'] = float(w['end']) - start_time
                    clip_words.append(new_w)
            
            logger.info(f"      ✅ Word slicing completed in {time.time() - t_slice:.2f}s (Total words: {len(clip_words)})")
            
            translated_words = clip_words

            

            # 3.9 SECOND: Framing on the extracted clip (Ahora Ultra Rápido con modelos compartidos)
            t_frame = time.time()
            # Pasamos los detectores compartidos para no recargarlos
            framing_data = analyze_framing_high_precision_local(
                V_OUT, 0.0, end_time - start_time, 
                is_podcast=is_podcast_global,
                detector=shared_detector,
                face_detector=shared_face_detector
            )
            logger.info(f"      🎞️ Framing analysis completed in {time.time() - t_frame:.2f}s")
            
            # 3.85 Process B-roll Suggestions and Adjust Times
            edit_events = analysis.get("edit_events", {"zooms": [], "icons": [], "b_rolls": [], "backgrounds": []})
            for key, event_list in edit_events.items():
                if isinstance(event_list, list):
                    for event in event_list:
                        if 'time' in event:
                            event['time'] = max(0.0, float(event['time']) - start_time)

            # 3.10 Store complete data for this clip
            clip_data = {
                **analysis,
                "duration": end_time - start_time,
                "words": translated_words,
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
            
            processed_clips.append(clip_data)

        # 4. Limpieza de IA
        shared_detector.close()
        shared_face_detector.close()

        final_data = {
            "clips": processed_clips,
            "version": version,
            "user_id": user_id,
            "video_title": video_title_for_ai,
            "is_podcast": is_podcast_global,
            "niche_name": initial_niche or "Generic",
            "instagram_handle": "rocotoclip",
            # For backward compatibility, keep top clip markers at root
            "words": processed_clips[0]["words"] if processed_clips else [],
            "words_es": processed_clips[0]["words_es"] if processed_clips else [],
            "video_url": processed_clips[0]["video_url"] if processed_clips else "",
            "audio_url": processed_clips[0]["audio_url"] if processed_clips else ""
        }

        # Ensure niche_name exists to avoid frontend errors
        if not final_data.get("niche_name"): final_data["niche_name"] = "Generic"
        
        with open(TRANSCRIPT_FILE, "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        
        # SECURITY: Removed global transcript_data.json write.
        # Each user's data stays isolated in transcript_{version}.json only.

        total_seconds = time.time() - global_start
        mins = int(total_seconds // 60)
        secs = int(total_seconds % 60)
        time_str = f"{mins} min {secs} seg" if mins > 0 else f"{secs} seg"

        logger.info("")
        logger.info("   🏁 PIPELINE FINISHED SUCCESSFULY")
        logger.info(f"   ⏱️ TOTAL TIME: {time_str}")
        logger.info("   ──────────────────────────────────────────────────────────────────")
        logger.info("")

        # Force flush log
        for l in logger.handlers:
            l.flush()

    except Exception as e:
        logger.error("CRITICAL ERROR: Pipeline failed dramatically.")
        logger.error(traceback.format_exc())
        sys.exit(1)
