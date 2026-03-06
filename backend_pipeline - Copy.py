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
from groq import Groq
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

def extract_audio(video_path, output_audio_path=None, format="wav"):
    """Extracts audio from video to a temporary WAV or MP3 file."""
    if output_audio_path is None:
        ext = "wav" if format == "wav" else "mp3"
        output_audio_path = video_path.rsplit('.', 1)[0] + f"_temp_audio.{ext}"
    
    logger.info(f"Extracting audio ({format}): {output_audio_path}...")
    try:
        if format == "wav":
            command = [
                "ffmpeg", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                "-y", output_audio_path
            ]
        else: # mp3
            # Low bitrate (32k) is plenty for Whisper and keeps file size very small
            command = [
                "ffmpeg", "-i", video_path,
                "-vn", "-acodec", "libmp3lame", "-b:a", "32k", "-ar", "16000", "-ac", "1",
                "-y", output_audio_path
            ]
            
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_audio_path
    except Exception as e:
        logger.error(f"Failed to extract audio: {str(e)}")
        return None

def transcribe_with_gemini(video_path):
    """Transcribes video using Gemini 3.1 Flash (Parallel & Ultra Fast)."""
    logger.info(f"Transcribing {video_path} using Gemini 3.1 Flash Lite...")
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    temp_audio = extract_audio(video_path, format="wav")
    if not temp_audio:
        raise ValueError("Could not extract audio for Gemini transcription.")
    
    try:
        # 1. Upload file to Gemini
        uploaded_file = client.files.upload(file=temp_audio)
        
        # 2. Wait for processing (usually instant for audio)
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(1)
            uploaded_file = client.files.get(name=uploaded_file.name)
            
        # 3. Request Transcription
        prompt = """
        Transcribe this audio EXACTLY as it is. 
        Provide a JSON output with the following structure:
        {
            "language": "en/es/etc",
            "segments": [
                {
                    "text": "The spoken sentence",
                    "start": 0.0,
                    "end": 3.0
                }
            ]
        }
        RULES:
        - Include MUST filler words (ums, ahs).
        - Break segments every 3-4 seconds MAX. Short segments are critical for sync.
        - Ensure timestamps are strictly accurate to the audio.
        """
        
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        
        # Parse text (removing potential markdown code blocks)
        raw_text = response.text.strip('`').replace('json\n', '', 1).strip()
        result = json.loads(raw_text)
        
        # 4. Convert to Whisper-like format (word interpolation)
        all_words = []
        segments_data = []
        full_text = ""
        
        for seg in result.get("segments", []):
            text = seg.get("text", "")
            start = float(seg.get("start", 0))
            end = float(seg.get("end", start + 1))
            full_text += text + " "
            
            raw_words = text.split()
            seg_words = []
            if raw_words:
                word_dur = (end - start) / len(raw_words)
                for i, w in enumerate(raw_words):
                    w_obj = {
                        "word": w.strip(),
                        "start": start + (i * word_dur),
                        "end": start + ((i + 1) * word_dur)
                    }
                    all_words.append(w_obj)
                    seg_words.append(w_obj)
            
            segments_data.append({
                "text": text,
                "start": start,
                "end": end,
                "words": seg_words
            })
            
        # Cleanup
        try: os.remove(temp_audio)
        except: pass
        
        return {
            "text": full_text.strip(),
            "words": all_words,
            "segments": segments_data,
            "language": result.get("language", "en")
        }
        
    except Exception as e:
        logger.error(f"Gemini Transcription failed: {e}.")
        raise e

def transcribe_audio(video_path, model_size="base"):
    """
    Transcribes audio using Groq (Ultra-Fast) with Gemini/Local as fallback.
    Uses MP3 to avoid 25MB file limits for long audios.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    
    if api_key:
        logger.info(f"Transcribing {video_path} using Groq Whisper (Ultra-Fast)...")
        # Use MP3 for Groq to dodge the 25MB limit on large files
        temp_audio = extract_audio(video_path, format="mp3")
        
        if temp_audio:
            try:
                client = Groq(api_key=api_key)
                with open(temp_audio, "rb") as file:
                    transcription = client.audio.transcriptions.create(
                        file=(temp_audio, file.read()),
                        model="whisper-large-v3",
                        response_format="verbose_json",
                    )
                
                words = []
                segments_data = []
                full_text = transcription.text
                
                for segment in transcription.segments:
                    seg_words = []
                    # Groq verbose_json sometimes includes word-level data
                    if hasattr(segment, 'words') and segment.words:
                        for word in segment.words:
                            words.append({
                                "word": word['word'].strip(),
                                "start": word['start'],
                                "end": word['end']
                            })
                            seg_words.append(words[-1])
                    else:
                        # Fallback interpolation
                        text = segment['text']
                        start = segment['start']
                        end = segment['end']
                        raw_words = text.split()
                        if raw_words:
                            word_dur = (end - start) / len(raw_words)
                            for i, w in enumerate(raw_words):
                                w_obj = {
                                    "word": w.strip(),
                                    "start": start + (i * word_dur),
                                    "end": start + ((i + 1) * word_dur)
                                }
                                words.append(w_obj)
                                seg_words.append(w_obj)
                    
                    segments_data.append({
                        "text": segment['text'].strip(),
                        "start": segment['start'],
                        "end": segment['end'],
                        "words": seg_words
                    })
                
                try: os.remove(temp_audio)
                except: pass

                return {
                    "text": full_text.strip(),
                    "words": words,
                    "segments": segments_data,
                    "language": getattr(transcription, 'language', 'en')
                }

            except Exception as e:
                logger.error(f"Groq API failed: {e}. Falling back to LOCAL Whisper for precision...")
                try: os.remove(temp_audio)
                except: pass
                # Fallback directly to local Whisper to ensure word-level precision
                return transcribe_audio_local(video_path, model_size)

def transcribe_audio_local(video_path, model_size="base"):
    """Fallback local transcription using faster-whisper."""
    logger.info(f"Falling back to local faster-whisper ({model_size} model)...")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, info = model.transcribe(video_path, beam_size=5, word_timestamps=True)
        
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
            
            segments_data.append({
                "text": segment.text.strip(),
                "start": segment.start,
                "end": segment.end,
                "words": seg_words
            })
            
        return {
            "text": full_text.strip(),
            "words": words,
            "segments": segments_data,
            "language": info.language
        }
    except Exception as e:
        logger.error(f"Final local transcription fallback failed: {e}")
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

def translate_with_gemini_text(segments_data, source_lang="en"):
    """
    Refines/Translates transcript segments using Gemini (handles giant context better).
    Optimized for high fidelity and stability.
    """
    if not segments_data: return []
    logger.info(f"Translating/Refining transcript via Gemini Flash Lite (Batch Mode)...")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    # SAFE BATCH SIZE: Reduced to 600 segments for better stability
    BATCH_SIZE = 600 
    all_translated_words = []
    
    for i in range(0, len(segments_data), BATCH_SIZE):
        batch = segments_data[i : i + BATCH_SIZE]
        batch_map = {str(idx): s["text"] for idx, s in enumerate(batch)}
        
        prompt = f"""
        Act as a professional transcription refiner and literal translator. 
        TASK:
        1. If source is English, translate to Neutral Literal Spanish.
        2. If source is Spanish, fix technical spelling of AI/SaaS terms.
        
        STRICT RULES:
        - NO PARAPHRASING. Keep the speaker's original style and filler words.
        - VERBATIM FIDELITY: Each segment must correspond exactly to the phonetic content.
        - TECHNICAL TERMS: ChatGPT, SaaS, AI, B-Roll, CRM, etc. must be correctly spelled.
        
        Segments (Index Mapping):
        {json.dumps(batch_map)}
        
        OUTPUT: Return ONLY a JSON object with same indices: {{"0": "texto", "1": "texto"}}
        """
        
        try:
            # Small delay to respect RPM limits
            if i > 0: time.sleep(2.0)
            
            response = client.models.generate_content(
                model='gemini-3.1-flash-lite-preview',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            translated_map = json.loads(response.text)
            
            for idx in range(len(batch)):
                idx_str = str(idx)
                trans_text = translated_map.get(idx_str)
                orig_seg = batch[idx]
                
                if not trans_text:
                    all_translated_words.extend(orig_seg.get("words", []))
                    continue
                
                trans_words = trans_text.split()
                duration = orig_seg["end"] - orig_seg["start"]
                word_dur = duration / len(trans_words) if trans_words else 0
                for w_idx, w_text in enumerate(trans_words):
                    all_translated_words.append({
                        "word": w_text,
                        "start": orig_seg["start"] + (w_idx * word_dur),
                        "end": orig_seg["start"] + ((w_idx + 1) * word_dur)
                    })
        except Exception as e:
            logger.error(f"Gemini translation failed for batch {i}: {e}. Keeping original words.")
            for s in batch: all_translated_words.extend(s.get("words", []))

    return all_translated_words

def translate_full_transcript_global(segments_data, source_lang="en"):
    """
    Unified entry point for transcript translation.
    Uses Gemini exclusively for stability and massive context handling.
    """
    if not segments_data: return []
    return translate_with_gemini_text(segments_data, source_lang)

# Global constants for Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def get_supabase_accounts(user_id=None):
    """Fetch user's social media accounts from Supabase to provide context to Gemini."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase credentials missing. Cannot fetch accounts.")
        return []
    
    url = f"{SUPABASE_URL}/rest/v1/accounts?select=id,name,niche"
    if user_id:
        url += f"&user_id=eq.{user_id}"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Failed to fetch accounts: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Error fetching accounts from Supabase: {e}")
    
    return []

def analyze_with_gemini(transcript, user_id=None, video_title="Unknown"):
    """
    ARQUITECTURA DE DOS FASES v4.0 (Estabilidad y Precisión)
    
    FASE 1: Selección Viral (Llamada 1) -> Hook / Hold / Reward y Tiempos.
    FASE 2: Enriquecimiento Visual (Llamada 2) -> Zooms / Iconos / B-Rolls.
    """
    logger.info(f"=== MOTOR DE INTELIGENCIA DUAL v4.0 (Título: {video_title}) ===")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")

    client = genai.Client(api_key=api_key)

    # --- PREPARACIÓN DE CONTEXTO ---
    # Obtenemos cuentas de usuario para detección de nicho
    accounts = get_supabase_accounts(user_id)
    accounts_json = json.dumps(accounts, indent=2) if accounts else "[]"
    
    # Calculamos límites de momentos intensos según la duración
    all_words = transcript.get('words', [])
    total_duration = all_words[-1]['end'] if all_words else 0
    
    # Sensible defaults for moments based on duration
    momentos_intensos_min = max(3, int(total_duration / 240))
    momentos_intensos_max = min(20, max(8, int(total_duration / 120)))
    
    length_instruction = "IMPORTANTE: Maximiza la retención con clips de 30 a 75 segundos. No selecciones fragmentos demasiado cortos que no cuenten una idea completa."

    # --- CONFIGURACIÓN DE PROMPTS ---

    # PROMPT 1: El original "literal" (Old) - NI UNA COMA MODIFICADA (Solo añadido el control de Título)
    PROMPT_SELECCION_LITERAL_OLD = """
Eres el mejor editor de contenido viral del mundo. Tu respuesta tiene DOS PASOS
que debes ejecutar EN ORDEN dentro de un único JSON.

TÍTULO DEL VÍDEO PARA CONTEXTO: {video_title}

PASO 1 → rellena el objeto "context" (tu razonamiento previo sobre el vídeo)
PASO 2 → rellena el array "clips" (tu selección final, usando el contexto del paso 1)

Este orden es obligatorio. Primero entiendes el vídeo, luego extraes los clips.

{length_instruction}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PASO 1 — ANÁLISIS DE CONTEXTO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Lee la transcripción completa y extrae:

- tema_central: una frase que resume de qué trata el vídeo
- tono: motivacional / educativo / polémico / narrativo / mixto
- angulo_unico: qué hace diferente a este creador vs. el resto del contenido del mismo tema
- datos_concretos: cualquier cifra, edad, cantidad, precio, porcentaje mencionado
- frases_gancho: las 5-8 frases literales más poderosas, las que podrían detener el scroll
- momentos_intensos: mínimo {momentos_intensos_min}, máximo {momentos_intensos_max} picos emocionales, revelaciones,
  contradicciones, historias personales o datos impactantes con sus timestamps
- is_podcast: true si detectas un diálogo/entrevista entre 2 o más personas, 
  false si es un monólogo, un solo narrador hablando a cámara o un tutorial.
  
- account_id: Elije el ID de la cuenta de esta lista que mejor encaja con el nicho del video:
  {accounts_json}
  Si ninguna encaja bien, pon null.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PASO 2 — EXTRACCIÓN DE CLIPS VIRALES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Usando el análisis del Paso 1 como guía, selecciona los fragmentos que puedan
convertirse en shorts que la gente no pueda dejar de ver, que comenten,
que guarden y que compartan.

MISIÓN PRIORITARIA — EL CLIP DEL TÍTULO (OBLIGATORIO):
Tu primera tarea es rastrear toda la transcripción para encontrar el segmento que justifica y cumple la promesa del título del video: "{video_title}". 
- Este fragmento DEBE ser uno de los clips extraídos, sin excepción.
- Márcalo estrictamente con "is_title_clip": true.
- Si el título dice algo específico (ej: "Con este negocio me compré una casa"), busca el momento exacto donde se habla de ello y asegúrate de que esté en la lista.

LOS 3 PILARES DEL SHORT VIRAL EN 2026:

PILAR 1 — HOOK (primeros 3 segundos): EL MÁS IMPORTANTE
El algoritmo mide qué porcentaje de espectadores pasan los 3 primeros segundos.
Sin gancho fuerte el clip no existe, no importa qué tan bueno sea el resto.

Tipos de gancho (en orden de efectividad):
1. CONTRAINTUITIVO — contradice lo que el espectador cree que es verdad
   Ej: "Las metas están sobrevaloradas" / "La motivación es una mentira"
2. DATO_IMPACTO — cifra específica + historia personal
   Ej: "Tenía 5.7€ en mi cuenta y a los 21 años gané mi primer millón"
3. PREGUNTA_DOLOR — pregunta que el espectador no puede ignorar porque lo describe
   Ej: "¿Por qué hay gente con menos talento que tú ganando más dinero?"
4. DIAGNOSTICO — nombrar el problema exacto que el espectador tiene
   Ej: "El problema no es que no tengas tiempo. Es que dependes de la motivación."
5. LOOP_ABIERTO — empezar algo y no terminarlo en los primeros 3s
   Ej: "Déjame contarte por qué casi pierdo todo lo que construí..."

PILAR 2 — HOLD (segundos 3-45): MANTENER LA RETENCIÓN
La retención cae si hay más de 8 segundos sin una frase de alto valor.
Un buen fragmento tiene una idea nueva o giro cada 8-10 segundos,
usa storytelling (situación → conflicto → resolución), e incluye datos concretos.

PILAR 3 — REWARD (últimos 5 segundos): TRIGGER DE COMPARTIR
Los vídeos que se comparten terminan con una verdad incómoda, un consejo
accionable, o una frase que resume algo que el espectador sentía pero no podía articular.

SISTEMA DE PUNTUACIÓN — UMBRAL ÚNICO >= 5:

HOOK (máx 9 pts):
+3 primera frase contradice creencia común o genera disonancia cognitiva
+3 contiene dato concreto (cifra, edad, cantidad) en los primeros 10 segundos
+2 hace pregunta que describe exactamente el dolor del espectador
+1 tiene loop abierto que obliga a seguir viendo

HOLD (máx 6 pts):
+3 historia personal completa (situación → problema → resolución)
+2 giro narrativo o revelación que cambia el marco de la idea
+1 alta densidad de valor (varias ideas fuertes en poco tiempo)

REWARD (máx 4 pts):
+2 genera debate o comentarios ("¿esto es verdad?", "yo también pasé por esto")
+2 termina con frase que el espectador quiere guardar o enviar a alguien

PENALIZACIONES:
-2 primeros 3 segundos débiles, genéricos o de introducción
-2 más de 10 segundos consecutivos sin frase de alto valor
-1 clip depende de contexto muy específico que el espectador no tiene

UMBRAL: válido SOLO si score >= 5.

DURACIÓN: MÍNIMO 23s | IDEAL 40-60s | MÁXIMO 75s
Si una idea poderosa dura más de 75s, extrae el sub-fragmento más intenso.

AUTONOMÍA NARRATIVA FLEXIBLE:
Se permiten referencias a conceptos universales (dinero, tiempo, éxito, fracaso,
relaciones, salud). NO referencias a personas o eventos específicos sin explicar.

DIVERSIDAD TEMÁTICA:
Cada clip debe tener un ángulo diferente. No selecciones dos clips que digan
esencialmente lo mismo aunque estén en distintos momentos del vídeo.

CLASIFICACIÓN (máx 2 etiquetas por clip):
- EXPLOSION: Desafía narrativa dominante, puede generar desacuerdo
- AUTORIDAD: Framework mental claro, enseña psicología o lógica fuerte
- CONVERSION: Identifica dolor específico, señala error concreto, CTA implícito
MIX IDEAL: 50% EXPLOSION | 30% AUTORIDAD | 20% CONVERSION

TÍTULOS: En español, orientados a búsqueda social real.
Ej: "¿Por qué siempre abandono mis metas?" > "Cómo tener éxito"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORMATO DE SALIDA JSON — ESTRUCTURA OBLIGATORIA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Devuelve SIEMPRE este objeto completo. Primero "context", luego "clips".
Si ningún clip alcanza score >= 5, devuelve "clips" como array vacío.

{{
  "context": {{
    "tema_central": "<string>",
    "is_podcast": <boolean>,
    "account_id": <number|null>,
    "tono": "<string>",
    "angulo_unico": "<string>",
    "datos_concretos": ["<string>"],
    "frases_gancho": ["<string>"],
    "momentos_intensos": [
      {{
        "tiempo_inicio": 0.0,
        "tiempo_fin": 0.0,
        "descripcion": "<string>"
      }}
    ]
  }},
  "clips": [
    {{
      "id": 1,
      "title": "<Título en español para búsqueda social>",
      "start": 0.0,
      "end": 0.0,
      "score": 0,
      "is_title_clip": <boolean>,
      "hook_type": "<CONTRAINTUITIVO / DATO_IMPACTO / PREGUNTA_DOLOR / DIAGNOSTICO / LOOP_ABIERTO>",
      "score_breakdown": {{
        "hook": 0,
        "hold": 0,
        "reward": 0,
        "penalties": 0
      }},
      "score_factors": ["<factor>"],
      "classification": ["EXPLOSION"],
      "dominant_emotion": "<indignación / revelación / validación / urgencia / esperanza>",
      "virality_level": 8,
      "reasoning": "<Por qué puede volverse viral — 1-2 líneas en español>",
      "comment_trigger": "<La frase que va a generar más comentarios>"
    }}
  ]
}}

Ordena los clips de MAYOR a MENOR score.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TRANSCRIPCIÓN — SEGMENTOS
(usa para entender la narrativa y seleccionar clips)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{transcript_text}
"""

    # PROMPT 2: La nueva versión experimental (Lite) - SENIOR VIRAL STRATEGIST
    PROMPT_SELECCION_LITE = """
Act like a senior estratega de contenido viral, editor de video short-form y analista de retención para plataformas como YouTube Shorts, Instagram Reels y TikTok.

Tu objetivo es analizar una transcripción completa de un video largo (long-form content) y detectar los fragmentos con mayor probabilidad de volverse virales cuando se convierten en contenido corto.

{length_instruction}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK: Analiza la transcripción y extrae los clips junto con su análisis estratégico.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1) Realiza un análisis profundo del contenido para entender:
- Tema principal del video
- Tono del creador (educativo, polémico, inspirador, confrontativo, etc.)
- Ángulo único o diferenciador del mensaje
- Momentos de alta intensidad emocional o cognitiva
- Patrones de narrativa o storytelling

2) Identifica los segmentos con MAYOR potencial viral basándote en estos disparadores psicológicos:

- CONTROVERSIA O POLÉMICA: Momentos donde el creador desafía creencias comunes o rompe paradigmas.
- STORYTELLING TRANSFORMACIONAL: Historias de cambio personal, éxito, fracaso o superación.
- AUTORIDAD Y PSICOLOGÍA: Revelación de errores comunes o patrones de comportamiento.
- EMOCIÓN INTENSA: Momentos que generen indignación, sorpresa, esperanza o urgencia.

3) Para cada clip seleccionado:
- Condensa el mensaje al núcleo más poderoso e identifica el hook natural.
- Asegúrate de que el clip funcione de manera independiente.
- Duración ideal: entre 25 y 90 segundos.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORMATO DE SALIDA JSON (ESTRICTO)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Devuelve UNICAMENTE el JSON sin explicación adicional.

{{
  "context": {{
    "tema_central": "<string>",
    "is_podcast": <boolean>,
    "account_id": <number|null>,
    "tono": "<string>",
    "angulo_unico": "<string>",
    "datos_concretos": ["<string>"],
    "frases_gancho": ["<string>"],
    "momentos_intensos": [{{ "tiempo_inicio": 0.0, "tiempo_fin": 0.0, "descripcion": "<string>" }}]
  }},
  "clips": [
    {{
      "id": <int>,
      "title": "<Título AGRESIVO y de alto CTR en español>",
      "start": 0.0,
      "end": 0.0,
      "score": <int 1-10>,
      "hook_type": "<CONTRAINTUITIVO / STORYTELLING / AUTORIDAD / POLEMICA / REVELACION>",
      "classification": ["EXPLOSION/AUTORIDAD/CONVERSION"],
      "dominant_emotion": "<indignación/esperanza/revelación/urgencia>",
      "reasoning": "<Análisis estratégico de retención>",
      "comment_trigger": "<La frase exacta que herirá el ego o despertará el debate>"
    }}
  ]
}}

Constraints:
- Títulos agresivos, directos y provocativos en español.
- No inventes contenido.
- Prioriza calidad viral.

Transcripción para procesar:
{transcript_text}
"""

    try:
        # Preparar transcripción
        transcript_text = "\n".join(
            f"[{s['start']:.1f}s - {s['end']:.1f}s] {s['text']}"
            for s in transcript['segments']
        )
        all_words = transcript['words']
        total_words = len(all_words)
        video_duration_min = (all_words[-1]['end'] / 60.0) if all_words else 0
        
        # --- LÓGICA DE SELECCIÓN DE MODELO Y PROMPT ---
        MODELO_SELECCIONADO = 'gemini-2.5-flash' # OPCIONES: 'gemini-2.5-flash', 'gemini-3.1-flash-lite-preview'
        USAR_PROMPT_LITE = False  # True para el nuevo prompt emocional | False para el literal antiguo
        # -----------------------------------------------

        # Muestreo representativo para FASE 1
        max_words = 4000 if video_duration_min > 40 else 3000
        if total_words <= max_words:
            sampled_words = all_words
        else:
            step = total_words / max_words
            sampled_words = [all_words[int(i * step)] for i in range(max_words)]
        
        transcript_words_json = json.dumps(sampled_words, ensure_ascii=False)

        if video_duration_min > 40:
            length_instruction = f"¡ALERTA CRÍTICA! Este es un VÍDEO MUY LARGO ({video_duration_min:.1f} minutos). Tienes la OBLIGACIÓN ABSOLUTA de extraer TODOS los momentos virales, que suelen ser ENTRE 15 Y 25 CLIPS INDIVIDUALES."
        else:
            length_instruction = "Extrae todos los clips buenos que encuentres, si tiene calidad extrae mínimo 3 a 8 clips o más si aplicase."

        # Construir prompt final
        if USAR_PROMPT_LITE:
            prompt_selection = PROMPT_SELECCION_LITE.format(
                length_instruction=length_instruction,
                transcript_text=transcript_text
            )
        else:
            prompt_selection = PROMPT_SELECCION_LITERAL_OLD.format(
                video_title=video_title,
                length_instruction=length_instruction,
                momentos_intensos_min=(6 if video_duration_min > 40 else 3),
                momentos_intensos_max=(25 if video_duration_min > 40 else 10),
                accounts_json=json.dumps(get_supabase_accounts(user_id), ensure_ascii=False),
                transcript_text=transcript_text
            )

        # --- LLAMADA 1: SELECCIÓN VIRAL ---
        logger.info(f"Fase 1: {'PROMPT LITE' if USAR_PROMPT_LITE else 'PROMPT LITERAL OLD'} con {MODELO_SELECCIONADO}...")
        
        response_1 = client.models.generate_content(
            model=MODELO_SELECCIONADO,
            contents=prompt_selection,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        
        selection_result = json.loads(response_1.text)
        raw_clips = selection_result.get("clips", [])
        
        # Filtrado inicial por score y duración 25-90s 
        valid_clips = []
        for c in raw_clips:
            if c.get("score", 0) >= 5:
                dur = float(c.get('end', 0)) - float(c.get('start', 0))
                if 25 <= dur <= 90:
                    valid_clips.append(c)
        
        if not valid_clips:
            logger.warning("No se encontraron clips virales en la Fase 1.")
            return selection_result

        logger.info(f"Fase 1 completa. Iniciando Enriquecimiento Visual...")

        # --- LLAMADA 2: ENRIQUECIMIENTO VISUAL ---
        prompt_effects = """
Eres un experto en diseño audiovisual. Tu tarea es inyectar efectos visuales a una lista de clips ya seleccionados.

MICRO-MOVIMIENTOS: Zooms/cortes cada 2-4s para mantener engagement visual.

ICONOS: 4-7 iconos por clip alineados con las palabras clave.
KEYWORDS DISPONIBLES: 'money', 'cash', 'rich', 'idea', 'think', 'mind', 'warning',
'alert', 'danger', 'stop', 'no', 'error', 'wrong', 'check', 'yes', 'correct', 'ok',
'time', 'clock', 'fast', 'speed', 'heart', 'love', 'hot', 'rocket', 'growth', 'up',
'down', 'work', 'task', 'office', 'success', 'win', 'star', 'laugh', 'funny', 'lol',
'wow', 'shock', 'amazing', 'cool', 'look', 'eye', 'sad', 'bad', 'cry', 'phone',
'computer', 'tech', 'camera', 'video', 'mic', 'search', 'find', 'link', 'lock',
'shield', 'tool', 'fix', 'build', 'book', 'learn', 'write', 'news', 'mail', 'chat',
'home', 'world', 'travel', 'sun', 'moon', 'star_special', 'music', 'sound',
'gift', 'party', 'health'

EDIT_EVENTS — REGLA CRÍTICA:
Los "time" de zooms e iconos deben corresponder exactamente al "start" de una
palabra real en la sección PALABRAS CON TIMESTAMPS al final de este prompt.
NO inventes tiempos. Usa solo timestamps que existan en esa lista.

LISTA DE CLIPS PARA PROCESAR:
{clips_json}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TRANSCRIPCIÓN — PALABRAS CON TIMESTAMPS PRECISOS
(usa SOLO esto para los "time" de zooms e iconos en edit_events)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{transcript_words_json}

FORMATO OBLIGATORIO DE RESPUESTA JSON:
{{
  "effects_map": [
    {{
      "id": <id_del_clip>,
      "edit_events": {{
        "zooms": [{{"time": <float>, "type": "in", "intensity": 0.5}}],
        "icons": [{{"time": <float>, "keyword": "keyword", "layout": "center", "duration": 1.5}}],
        "b_rolls": [{{"time": <float>, "query": "English Pexels search query", "duration": 3.0}}]
      }}
    }}
  ]
}}
"""
        
        # Formatear el prompt de efectos
        prompt_effects_final = prompt_effects.format(
            clips_json=json.dumps([{ "id": c["id"], "start": c["start"], "end": c["end"], "title": c["title"] } for c in valid_clips], ensure_ascii=False),
            transcript_words_json=transcript_words_json
        )

        response_2 = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt_effects_final,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        
        effects_result = json.loads(response_2.text)
        effects_map = {e["id"]: e["edit_events"] for e in effects_result.get("effects_map", [])}

        # Unir los clips con sus efectos
        for c in valid_clips:
            c["edit_events"] = effects_map.get(c["id"], {"zooms": [], "icons": [], "b_rolls": []})
        
        selection_result["clips"] = valid_clips
        
        # Log final del motor dual
        logger.info(f"Fase 2 completa.")
        
        return selection_result

    except Exception as e:
        err_msg = f"Error procesando respuesta de Gemini. Error: {str(e)}"
        if 'response_1' in locals() and hasattr(response_1, 'text'):
            err_msg += f" | Respuesta 1 raw: {response_1.text[:500]}..."
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
      1. La palabra empieza con mayúscula (inicio de oración)
      2. Hay una pausa larga antes de la palabra (>0.4s entre palabras)
    Siempre retrocede al candidato más reciente antes del start_time
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
    
    args = parser.parse_known_args()[0]
    
    youtube_url = args.url
    version = args.version or str(int(time.time()))
    user_id = args.user_id
    title = args.title
    initial_niche = args.niche

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
        if youtube_url:
            video_file = download_video(youtube_url, INPUT_FILE)
        elif os.path.exists("input_full.mp4"):
            video_file = "input_full.mp4"
            print("Using legacy input_full.mp4")
        else:
            # Fallback default
            youtube_url = "https://www.youtube.com/watch?v=okL1xL_hHOw"
            video_file = download_video(youtube_url, INPUT_FILE)
        logger.info(f"   ✅ [PHASE 1] Download completed in {time.time() - t_start:.2f}s")
        
        # 1.5 NOTE: No proxy needed — analyze_framing_high_precision_local already
        # downscales internally to INTERNAL_ANALYSIS_WIDTH (480px). Using a pre-scaled
        # proxy caused FPS mismatches and wrong frame timestamps vs the original file.
        # The validate_universal_fix.py approach (using the original video directly) is correct.
        logger.info(f"   ✅ [PHASE 1.5] Skipping proxy — framing will use original video directly (480px internal downscale)")
        
        # 2. Transcribe (Using Whisper for sub-second word precision)
        t_start = time.time()
        transcript = transcribe_audio(video_file, model_size="base")
        logger.info(f"   ✅ [PHASE 2] Transcription completed in {time.time() - t_start:.2f}s")
        
        # Phase 2.5 Skipped per user request (Direct from Whisper to Analysis)

        # 3. Analyze Transcript with Gemini (New v3.0 logic with context and account detection)
        t_start = time.time()
        analysis_result = analyze_with_gemini(transcript, user_id=user_id, video_title=title)
        logger.info(f"   ✅ [PHASE 3] Gemini Viral Analysis completed in {time.time() - t_start:.2f}s")
        
        context = analysis_result.get("context", {})
        raw_clips = analysis_result.get("clips", [])
        is_podcast_global = context.get("is_podcast", False)
        selected_account_id = context.get("account_id")
        video_title_final = context.get("tema_central", title)
        logger.info(f"GEMINI CONTEXT — Format: {'Podcast/Interview' if is_podcast_global else 'Monologue/Tutorial'}")

        if not analysis_result or not raw_clips:
            raise ValueError("Gemini failed to identify any viral clips.")
            
        # Sort by score desc (Gemini should already do this, but ensure it)
        raw_clips.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # NO hard limit — clips are already filtered by score ≥ 4 in analyze_with_gemini
        logger.info(f"Processing {len(raw_clips)} clips that passed peak moment scoring (score ≥ 5)")
        
        # 3.4 Inicialización ÚNICA de IA de Framing (Optimización de Flujo Invertido)
        logger.info("Inicializando modelos de IA para framing (una sola carga)...")
        from mediapipe.tasks.python import vision
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "efficientdet_lite0.tflite")
        face_model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blaze_face_short_range.tflite")
        
        det_options = vision.ObjectDetectorOptions(base_options=mp.tasks.BaseOptions(model_asset_path=model_path), score_threshold=0.3)
        face_options = vision.FaceDetectorOptions(base_options=mp.tasks.BaseOptions(model_asset_path=face_model_path), min_detection_confidence=0.4)
        
        shared_detector = vision.ObjectDetector.create_from_options(det_options)
        shared_face_detector = vision.FaceDetector.create_from_options(face_options)

        processed_clips = []
        
        for idx, analysis in enumerate(raw_clips):
            logger.info(f"--- Processing Clip #{idx+1} (Score: {analysis.get('score')}) ---")
            
            # Clip-specific filenames
            clip_id = idx + 1
            V_OUT = os.path.join(CLIPS_DIR, f"video_{version}_clip_{clip_id}.mp4")
            A_OUT = os.path.join(CLIPS_DIR, f"audio_{version}_clip_{clip_id}.wav")
            
            # 3.5 Adjust Transcript Timestamps
            start_time = float(analysis.get('start', 0.0))
            # Snap al inicio de frase más cercano — evita cortes en medio de oración
            start_time = snap_to_sentence_start(start_time, transcript['words'])
            end_time = float(analysis.get('end', start_time + 30.0))
            
            adjusted_words = []
            for w in transcript['words']:
                if w['end'] > start_time and w['start'] < end_time:
                    adjusted_words.append({
                        "word": w['word'],
                        "start": max(0.0, w['start'] - start_time),
                        "end": w['end'] - start_time
                    })
            
            # 3.7 Extract Words from Original Transcript (CLONE to avoid shared mutation)
            translated_words = [
                {**w, "start": max(0.0, w["start"] - start_time), "end": w["end"] - start_time} 
                for w in transcript["words"] 
                if w['end'] > start_time and w['start'] < end_time
            ]
            
            # 3.8 FIRST: Crop and Cut the physical clip (Lossless)
            t_clip = time.time()
            process_video_ffmpeg(video_file, V_OUT, start_time, end_time, A_OUT)
            logger.info(f"      ✅ Clip extraction completed in {time.time() - t_clip:.2f}s")

            # 3.9 SECOND: Framing on the extracted clip (Ahora Ultra Rápido con modelos compartidos)
            t_frame = time.time()
            # Pasamos los detectores compartidos para no recargarlos
            framing_data = analyze_framing_high_precision_local(
                V_OUT, 0, end_time - start_time, 
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
            
            if clip_data.get("is_title_clip"):
                logger.info(f"      📍 [Title Match] This clip matches the video title: '{video_title_final}'")
            
            processed_clips.append(clip_data)

        # 4. Limpieza de IA
        shared_detector.close()
        shared_face_detector.close()

        # Detect which index is the title clip and reposition it to the first spot
        title_clip = next((c for c in processed_clips if c.get("is_title_clip")), None)
        other_clips = [c for c in processed_clips if not c.get("is_title_clip")]
        
        # Sort ONLY the other clips by score desc
        other_clips.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # Final list: Title Clip first (if found), then the rest by score
        final_clips = ([title_clip] if title_clip else []) + other_clips
        title_clip_idx = 0 if title_clip else None

        final_data = {
            "clips": final_clips,
            "version": version,
            "user_id": user_id,
            "video_title": video_title_final,
            "account_id": selected_account_id,
            "is_podcast": is_podcast_global,
            "niche_name": initial_niche,
            "title_clip_index": title_clip_idx,
            # For backward compatibility, keep top clip markers at root (now Title Clip if exists)
            "words": final_clips[0]["words"] if final_clips else [],
            "words_es": final_clips[0]["words_es"] if final_clips else [],
            "video_url": final_clips[0]["video_url"] if final_clips else "",
            "audio_url": final_clips[0]["audio_url"] if final_clips else ""
        }

        # If we have an account_id detected or a niche provided, enrich the manifest
        if final_data["account_id"]:
            # Try to get niche details
            accounts = get_supabase_accounts(user_id)
            acc = next((a for a in accounts if str(a['id']) == str(final_data["account_id"])), None)
            if acc:
                final_data["instagram_handle"] = acc.get("name")
                final_data["niche_name"] = acc.get("niche")
        elif initial_niche:
            # If no account detected but niche specified, use it
            final_data["niche_name"] = initial_niche
        
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
