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
import sys
import traceback
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

def transcribe_with_groq(video_path):
    """Transcribes audio using Groq Whisper (Ultra-Fast & High Precision)."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY missing.")

    # Use MP3 to stay under 25MB limit
    temp_audio = extract_audio(video_path, format="mp3")
    if not temp_audio:
        raise ValueError("Audio extraction failed for Groq.")

    try:
        # Check size (Groq limit is 25MB)
        if os.path.getsize(temp_audio) > 20 * 1024 * 1024:
            raise ValueError("Audio file too large for Groq (>20MB).")

        logger.info(f"Transcribing {video_path} via Groq API...")
        client = Groq(api_key=api_key)
        with open(temp_audio, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(temp_audio, file.read()),
                model="whisper-large-v3",
                response_format="verbose_json",
            )
        
        words = []
        segments_data = []
        
        # Groq returns segments in verbose_json
        for seg in transcription.segments:
            seg_start = seg['start']
            seg_end = seg['end']
            seg_text = seg['text'].strip()
            
            # Word-level fallback (Groq sometimes has it, but interpolation is safer if missing)
            raw_words = seg_text.split()
            seg_words = []
            if raw_words:
                word_dur = (seg_end - seg_start) / len(raw_words)
                for i, w in enumerate(raw_words):
                    w_obj = {
                        "word": w.strip(),
                        "start": seg_start + (i * word_dur),
                        "end": seg_start + ((i + 1) * word_dur)
                    }
                    words.append(w_obj)
                    seg_words.append(w_obj)
            
            segments_data.append({
                "text": seg_text,
                "start": seg_start,
                "end": seg_end,
                "words": seg_words
            })

        return {
            "text": transcription.text,
            "words": words,
            "segments": segments_data,
            "language": transcription.language
        }
    finally:
        if temp_audio and os.path.exists(temp_audio):
            os.remove(temp_audio)

def transcribe_audio_local(video_path, model_size="base"):
    """Original Local Whisper transcription."""
    logger.info(f"Transcribing {video_path} locally (Whisper {model_size})...")
    from faster_whisper import WhisperModel
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
    Transcribes audio EXCLUSIVELY using local faster-whisper.
    """
    return transcribe_audio_local(video_path, model_size)

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



def analyze_with_gemini(transcript, user_id=None, video_title="Unknown"):
    """
    MOTOR DE EXTRACCIÓN VIRAL v3.0 - Llamada unica con chain-of-thought

    Una sola llamada a Gemini. El JSON de salida tiene dos secciones:
      "context" - razonamiento previo: Gemini analiza el video completo
                  antes de seleccionar nada.
      "clips"   - extraccion final: usando el contexto como guia.

    El orden en el JSON obliga al modelo a pensar antes de decidir.
    Mismo beneficio que dos llamadas, un solo API call.

    Score unificado: umbral unico >= 5 en prompt y en codigo.
    Sin limite fijo de clips - la calidad es el unico filtro.
    """
    logger.info("=== MOTOR DE EXTRACCIÓN VIRAL v3.0 ===")
    logger.info("Iniciando análisis viral (llamada única con chain-of-thought)...")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")

    client = genai.Client(api_key=api_key)

    # Transcripción en dos formatos:
    # 1. Segmentos legibles — para análisis narrativo y selección de clips
    transcript_text = "\n".join(
        f"[{s['start']:.1f}s - {s['end']:.1f}s] {s['text']}"
        for s in transcript['segments']
    )
    # 2. Words con timestamps precisos — para anclar zooms e iconos a momentos exactos
    # Muestreo dinámico basado en duración real del vídeo:
    # - Vídeos cortos (<20 min): todos los words sin límite
    # - Vídeos medianos (20-40 min): muestra representativa de 3.000 words
    # - Vídeos largos (>40 min): muestra representativa de 4.000 words
    # La muestra es DISTRIBUIDA uniformemente (no truncada), para que Gemini
    # vea el inicio, el medio y el final con igual atención.
    all_words = transcript['words']
    total_words = len(all_words)
    video_duration_min = (all_words[-1]['end'] / 60.0) if all_words else 0

    if video_duration_min <= 20:
        # Video corto - enviar todo
        sampled_words = all_words
        length_instruction = "Extrae todos los buenos clips que encuentres, al menos 3 a 5 si tienen calidad."
    else:
        # Video largo - muestra distribuida uniformemente
        max_words = 4000 if video_duration_min > 40 else 3000
        if total_words <= max_words:
            sampled_words = all_words
        else:
            # Calcular paso de muestreo para distribuir uniformemente
            step = total_words / max_words
            sampled_words = [all_words[int(i * step)] for i in range(max_words)]

        logger.info(
            f"Video largo ({video_duration_min:.1f} min) - words muestreados: "
            f"{len(sampled_words)}/{total_words} (distribuidos uniformemente)"
        )
        
        if video_duration_min > 40:
            length_instruction = "¡ALERTA CRÍTICA! Este es un VÍDEO MUY LARGO (más de 40 minutos) lleno de valor. Tienes la OBLIGACIÓN ABSOLUTA de extraer TODOS los momentos virales, que suelen ser ENTRE 10 Y 25 CLIPS INDIVIDUALES. ¡NO seas perezoso! Revisa toda la hora."
        else:
            length_instruction = "¡ATENCIÓN! Este vídeo dura más de 20 minutos. Deberías encontrar un MÍNIMO de 8 a 15 clips de alta calidad. Extrae todos y cada uno de ellos."

    transcript_words = json.dumps(sampled_words, ensure_ascii=False)

    prompt = f"""
Eres el mejor editor de contenido viral del mundo. Tu respuesta tiene DOS PASOS
que debes ejecutar EN ORDEN dentro de un unico JSON.

PASO 1 -> rellena el objeto 'context' (tu razonamiento previo sobre el vídeo)
PASO 2 -> rellena el array 'clips' (tu seleccion final, usando el contexto del paso 1)

Este orden es obligatorio. Primero entiendes el video, luego extraes los clips.

TITULO DEL VIDEO (CONTEXTO): {video_title}

{length_instruction}

----------------------------------------
MISION ESPECIAL: EL CLIP DEL TITULO
----------------------------------------
Debes encontrar el momento exacto en el video que cumple la promesa del titulo: "{video_title}". 
- Este fragmento debe ser uno de los clips extraídos.
- Marcalo obligatoriamente con 'Is Title Clip: true'.
- IMPORTANTE: No limites el resto de la seleccion a este tema. Busca otros momentos virales independientes que cumplan los criterios de score >= 5.

----------------------------------------
PASO 1 - ANALISIS DE CONTEXTO
----------------------------------------

Lee la transcripcion completa y extrae:

- tema_central: una frase que resume de que trata el video
- tono: motivacional / educativo / polemico / narrativo / mixto
- angulo_unico: que hace diferente a este creador vs. el resto del contenido del mismo tema
- datos_concretos: cualquier cifra, edad, cantidad, precio, porcentaje mencionado
- frases_gancho: las 5-8 frases literales mas poderosas, las que podrian detener el scroll
- momentos_intensos: minimo {6 if video_duration_min > 40 else 3}, maximo {25 if video_duration_min > 40 else 10} picos emocionales, revelaciones,
  contradicciones, historias personales o datos impactantes con sus timestamps
- is_podcast: true si detectas un dialogo/entrevista entre 2 o mas personas, 
  false si es un monologo, un solo narrador hablando a camara o un tutorial.

----------------------------------------
PASO 2 - EXTRACCION DE CLIPS VIRALES
----------------------------------------


Usando el analisis del Paso 1 como guia, selecciona los fragmentos que puedan
convertirse en shorts que la gente no pueda dejar de ver, que comenten,
que guarden y que compartan.

LOS 3 PILARES DEL SHORT VIRAL EN 2026:

PILAR 1 - HOOK (primeros 3 segundos): EL MAS IMPORTANTE
El algoritmo mide que porcentaje de espectadores pasan los 3 primeros segundos.
Sin gancho fuerte el clip no existe, no importa que tan bueno sea el resto.

Tipos de gancho (en orden de efectividad):
1. CONTRAINTUITIVO - contradice lo que el espectador cree que es verdad
   Ej: 'Las metas estan sobrevaloradas' / 'La motivacion es una mentira'
2. DATO_IMPACTO - cifra especifica + historia personal
   Ej: 'Tenia 5.7 euros en mi cuenta y a los 21 anos gane mi primer millon'
3. PREGUNTA_DOLOR - pregunta que el espectador no puede ignorar porque lo describe
   Ej: 'Por que hay gente con menos talento que tu ganando mas dinero? '
4. DIAGNOSTICO - nombrar el problema exacto que el espectador tiene
   Ej: 'El problema no es que no tengas tiempo. Es que dependes de la motivacion.'
5. LOOP_ABIERTO - empezar algo y no terminarlo en los primeros 3 segundos
   Ej: 'Dejame contarte por que casi pierdo todo lo que construi...'

PILAR 2 - HOLD (segundos 3-45): MANTENER LA RETENCION
La retencion cae si hay mas de 8 segundos sin una frase de alto valor.
Un buen fragmento tiene una idea nueva o giro cada 8-10 segundos,
usa storytelling (situacion -> conflicto -> resolucion), e incluye datos concretos.

PILAR 3 - REWARD (ultimos 5 segundos): TRIGGER DE COMPARTIR
Los videos que se comparten terminan con una verdad incomoda, un consejo
accionable, o una frase que resume algo que el espectador sentia pero no podia articular.

SISTEMA DE PUNTUACION - UMBRAL UNICO >= 5:

HOOK (max 9 pts):
+3 primera frase contradice creencia comun o genera disonancia cognitiva
+3 contiene dato concreto (cifra, edad, cantidad) en los primeros 10 segundos
+2 hace pregunta que describe exactamente el dolor del espectador
+1 tiene loop abierto que obliga a seguir viendo

HOLD (max 6 pts):
+3 historia personal completa (situacion -> problema -> resolucion)
+2 giro narrativo o revelacion que cambia el marco de la idea
+1 alta densidad de valor (varias ideas fuertes en poco tiempo)

REWARD (max 4 pts):
+2 genera debate o comentarios ('esto es verdad?', 'yo tambien pase por esto')
+2 termina con frase que el espectador quiere guardar o enviar a alguien

PENALIZACIONES:
-2 primeros 3 segundos debiles, genericos o de introduccion
-2 mas de 10 segundos consecutivos sin frase de alto valor
-1 clip depende de contexto muy especifico que el espectador no tiene

UMBRAL: valido SOLO si score >= 5.

DURACION: MINIMO 25 segundos | IDEAL 45-60 segundos | MAXIMO 90 segundos
Si una idea poderosa dura mas de 90 segundos, extrae el sub-fragmento mas intenso.

AUTONOMIA NARRATIVA FLEXIBLE:
Se permiten referencias a conceptos universales (dinero, tiempo, exito, fracaso,
relaciones, salud). NO referencias a personas o eventos especificos sin explicar.

DIVERSIDAD TEMATICA:
Cada clip debe tener un angulo diferente. No selecciones dos clips que digan
esencialmente lo mismo aunque esten en distintos momentos del video.

CLASIFICACION (max 2 etiquetas por clip):
- EXPLOSION: Desafia narrativa dominante, puede generar desacuerdo
- AUTORIDAD: Framework mental claro, ensena psicologia o logica fuerte
- CONVERSION: Identifica dolor especifico, senala error concreto, CTA implicito
MIX IDEAL: 50% EXPLOSION | 30% AUTORIDAD | 20% CONVERSION

TITULOS: En espanol, orientados a busqueda social real.
Ej: 'Por que siempre abandono mis metas?' > 'Como tener exito'

MICRO-MOVIMIENTOS: Zooms/cortes cada 2-4 segundos para mantener engagement visual.

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

EDIT_EVENTS - REGLA CRITICA:
Los 'time' de zooms e iconos deben corresponder exactamente al 'start' de una
palabra real en la seccion PALABRAS CON TIMESTAMPS al final de este prompt.
NO inventes tiempos. Usa solo timestamps que existan en esa lista.

----------------------------------------
FORMATO DE SALIDA DE TEXTO (ETIQUETAS ESTRICTAS)
----------------------------------------

DEBES RESPONDER EXCLUSIVAMENTE CON TEXTO PLANO USANDO ETIQUETAS. ABSOLUTAMENTE NADA DE JSON O FORMATOS DE CODIGO.
Sigue esta plantilla sin desvios:

[CONTEXT_START]
Tema Central: <escribe el tema central>
Es Podcast: <true o false>
Tono: <describe el tono>
[CONTEXT_END]

Para cada clip que cumpla (Score minimo 5), crea un bloque asi:

[CLIP_START]
Title: <Titulo en espanol para busqueda social>
Start: <0.0>
End: <0.0>
Score: <0 a 11>
Is Title Clip: <true o false>
Hook Type: <CONTRAINTUITIVO / DATO_IMPACTO / PREGUNTA_DOLOR / DIAGNOSTICO / LOOP_ABIERTO>
Reasoning: <Minimo 1 linea de por que es viral>
Classification: <EXPLOSION / AUTORIDAD / CONVERSION>
---
Zoom: <time> | <in> | <0.5>
Icon: <time> | <keyword> | <layout> | <duration>
Broll: <time> | <English query> | <duration>
[CLIP_END]

Reglas para los EVENTOS (Zooms, Iconos, Brolls):
- Si no hay eventos, simplemente no escribas la linea.
- Usa los timestamps de las 'PALABRAS CON TIMESTAMPS' exactamente.
- Formato EXACTO separado por ' | '. Ejemplo: 'Icon: 15.5 | money | center | 1.5'.

Ordena los clips de MAYOR a MENOR score.

----------------------------------------
TRANSCRIPCION - SEGMENTOS
(usa para entender la narrativa y seleccionar clips)
----------------------------------------
{transcript_text}

----------------------------------------
TRANSCRIPCION - PALABRAS CON TIMESTAMPS PRECISOS
(usa SOLO esto para los 'time' de zooms e iconos en edit_events)
----------------------------------------
{transcript_words}
"""

    response = None
    max_retries = 3
    import re

    for attempt in range(max_retries):
        logger.info(f"Llamando a Gemini (Intento {attempt + 1}/{max_retries})...")
        time.sleep(1)
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="text/plain"),
            )

            raw_text = response.text.strip()
            
            # --- PARSEADOR ROBUSTO BASADO EN REGEX Y BLOQUES ---
            result = {
                "context": {},
                "clips": []
            }
            
            # 1. Parsear Contexto
            context_match = re.search(r'\[CONTEXT_START\](.*?)\[CONTEXT_END\]', raw_text, re.DOTALL)
            if context_match:
                ctx_text = context_match.group(1)
                
                # Extraer campos clave
                tema_match = re.search(r'Tema Central:\s*(.*)', ctx_text)
                podcast_match = re.search(r'Es Podcast:\s*(.*)', ctx_text, re.IGNORECASE)
                tono_match = re.search(r'Tono:\s*(.*)', ctx_text)
                
                if tema_match: result["context"]["tema_central"] = tema_match.group(1).strip()
                if podcast_match: result["context"]["is_podcast"] = "true" in podcast_match.group(1).lower()
                if tono_match: result["context"]["tono"] = tono_match.group(1).strip()
            
            # 2. Parsear Clips
            clips_blocks = re.findall(r'\[CLIP_START\](.*?)\[CLIP_END\]', raw_text, re.DOTALL)
            
            for idx, c_text in enumerate(clips_blocks):
                clip_obj = {
                    "id": idx + 1,
                    "title": "", "start": 0.0, "end": 0.0, "score": 0, "is_title_clip": False, "hook_type": "N/A",
                    "reasoning": "", "classification": [], "edit_events": {"zooms": [], "icons": [], "b_rolls": []}
                }
                
                # Campos directos
                for line in c_text.split('\n'):
                    line = line.strip()
                    if line.startswith('Title:'): clip_obj['title'] = line.replace('Title:', '').strip()
                    elif line.startswith('Start:'): 
                        try: clip_obj['start'] = float(line.replace('Start:', '').strip())
                        except: pass
                    elif line.startswith('End:'): 
                        try: clip_obj['end'] = float(line.replace('End:', '').strip())
                        except: pass
                    elif line.startswith('Score:'): 
                        try: clip_obj['score'] = float(line.replace('Score:', '').strip())
                        except: pass
                    elif line.startswith('Is Title Clip:'):
                        clip_obj['is_title_clip'] = 'true' in line.lower()
                    elif line.startswith('Hook Type:'): clip_obj['hook_type'] = line.replace('Hook Type:', '').strip()
                    elif line.startswith('Reasoning:'): clip_obj['reasoning'] = line.replace('Reasoning:', '').strip()
                    elif line.startswith('Classification:'): clip_obj['classification'] = [line.replace('Classification:', '').strip()]
                    
                    # Eventos
                    elif line.startswith('Zoom:'):
                        parts = [p.strip() for p in line.replace('Zoom:', '').split('|')]
                        if len(parts) >= 3:
                            try: clip_obj["edit_events"]["zooms"].append({"time": float(parts[0]), "type": parts[1], "intensity": float(parts[2])})
                            except: pass
                    elif line.startswith('Icon:'):
                        parts = [p.strip() for p in line.replace('Icon:', '').split('|')]
                        if len(parts) >= 4:
                            try: clip_obj["edit_events"]["icons"].append({"time": float(parts[0]), "keyword": parts[1], "layout": parts[2], "duration": float(parts[3])})
                            except: pass
                    elif line.startswith('Broll:'):
                        parts = [p.strip() for p in line.replace('Broll:', '').split('|')]
                        if len(parts) >= 3:
                            try: clip_obj["edit_events"]["b_rolls"].append({"time": float(parts[0]), "query": parts[1], "duration": float(parts[2])})
                            except: pass
                
                # Solo agregar si validó las métricas clave
                if clip_obj["score"] >= 5 and clip_obj["end"] > clip_obj["start"]:
                    result["clips"].append(clip_obj)

            # Loguear contexto si está disponible
            ctx = result.get("context", {})
            if ctx:
                logger.info(
                    f"Contexto extraído — Tema: '{ctx.get('tema_central', 'N/A')}' | "
                    f"Tono: {ctx.get('tono', 'N/A')} | "
                    f"Momentos intensos: {len(ctx.get('momentos_intensos', []))}"
                )

            if "clips" in result and len(result["clips"]) > 0:
                # Umbral único: score >= 5
                valid_clips = [c for c in result["clips"] if c.get("score", 0) >= 5]
                rejected_count = len(result["clips"]) - len(valid_clips)
                if rejected_count > 0:
                    logger.info(f"Filtrados {rejected_count} clips con score < 5")

                # Validar duración (margen de seguridad 25-90s)
                duration_valid = []
                for c in valid_clips:
                    clip_duration = float(c.get('end', 0)) - float(c.get('start', 0))
                    if 25 <= clip_duration <= 90:
                        duration_valid.append(c)
                    else:
                        logger.info(f"Clip descartado '{c.get('title', '')}' — duración {clip_duration:.1f}s fuera de rango")

                result["clips"] = duration_valid

                if duration_valid:
                    best = duration_valid[0]
                    logger.info(
                        f"Motor Viral v3.0 encontró {len(duration_valid)} clips válidos (score ≥ 5). "
                        f"Mejor: score={best.get('score')} | hook={best.get('hook_type')} | "
                        f"inicia en {best.get('start')}s"
                    )
                else:
                    logger.warning("Todos los clips filtrados — SIN CLIPS con intensidad suficiente")
            else:
                logger.warning("Gemini no encontró clips — INTENSIDAD INSUFICIENTE en la transcripción")

            return result

        except Exception as e:
            err_msg = f"Error en intento {attempt + 1}: {str(e)}"
            if response and hasattr(response, 'text'):
                err_msg += f" | Respuesta raw truncada: {response.text[-500:]}"
            logger.warning(err_msg)
            if attempt == max_retries - 1:
                logger.error("Se agotaron los reintentos de Gemini para análisis viral.")
                raise e
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
            video_file = download_video(youtube_url, INPUT_FILE)
        elif os.path.exists("input_full.mp4"):
            video_file = "input_full.mp4"
            print("Using legacy input_full.mp4")
        else:
            # Fallback default
            youtube_url = "https://www.youtube.com/watch?v=okL1xL_hHOw"
            video_file = download_video(youtube_url, INPUT_FILE)
        # --- FIN MODO TEST ---
        logger.info(f"   ✅ [PHASE 1] Download completed in {time.time() - t_start:.2f}s")
        
        # 1.5 NOTE: No proxy needed — analyze_framing_high_precision_local already
        # downscales internally to INTERNAL_ANALYSIS_WIDTH (480px). Using a pre-scaled
        # proxy caused FPS mismatches and wrong frame timestamps vs the original file.
        # The validate_universal_fix.py approach (using the original video directly) is correct.
        logger.info(f"   ✅ [PHASE 1.5] Skipping proxy — framing will use original video directly (480px internal downscale)")
        
        # 2. Transcribe
        t_start = time.time()
        transcript = transcribe_audio(video_file)
        logger.info(f"   ✅ [PHASE 2] Transcription completed in {time.time() - t_start:.2f}s")
            

        # 3. Analyze Transcript with Gemini (v3.0 logic with context and account detection)
        t_start = time.time()
        
        # Determine video title for Gemini context
        video_title_for_ai = title or "Unknown Video"
        if youtube_url and youtube_url != "Local Test File" and video_title_for_ai == "Unknown Video":
            try:
                with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                    info = ydl.extract_info(youtube_url, download=False)
                    video_title_for_ai = info.get('title', "Project")
            except: pass

        analysis_result = analyze_with_gemini(transcript, user_id=user_id, video_title=video_title_for_ai)
        logger.info(f"   ✅ [PHASE 3] Gemini Viral Analysis completed in {time.time() - t_start:.2f}s")
        
        context = analysis_result.get("context", {})
        raw_clips = analysis_result.get("clips", [])
        is_podcast_global = context.get("is_podcast", False)
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
            
            # 3.7 Extract Spanish Translation exactly for this clip using Gemini (Local Context + Short Segment Timestamps)
            t_trans = time.time()
            
            clip_segments = []
            for seg in transcript.get("segments", []):
                # Verificar traslape con los tiempos del clip actual
                if seg["end"] > start_time and seg["start"] < end_time:
                    c_start = max(0.0, seg["start"] - start_time)
                    c_end = seg["end"] - start_time
                    # Palabras que cayeron en este micro-segmento
                    seg_words = [w for w in adjusted_words if w['start'] >= c_start and w['end'] <= c_end]
                    
                    clip_segments.append({
                        "text": seg["text"].strip(),
                        "start": c_start,
                        "end": c_end,
                        "words": seg_words
                    })
            
            if clip_segments:
                try:
                    translated_words = translate_full_transcript_global(clip_segments, source_lang=transcript.get("language", "en"))
                    if not translated_words:
                        translated_words = adjusted_words
                except Exception as e:
                    logger.error(f"      ❌ Local Clip Translation failed: {e}. Using original words.")
                    translated_words = adjusted_words
            else:
                translated_words = adjusted_words
                
            logger.info(f"      ✅ Clip Contextual Translation completed in {time.time() - t_trans:.2f}s")
            
            # 3.8 FIRST: Crop and Cut the physical clip (Lossless)
            t_clip = time.time()
            process_video_ffmpeg(video_file, V_OUT, start_time, end_time, A_OUT)
            logger.info(f"      ✅ Clip extraction completed in {time.time() - t_clip:.2f}s")

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
