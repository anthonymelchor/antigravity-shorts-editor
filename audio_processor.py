import os
import random
import subprocess
import logging

logger = logging.getLogger(__name__)

def select_music_for_niche(niche_name, music_base_path):
    """
    Selects a random music file from the appropriate niche folder.
    """
    niche_map = {
        "Mentalidad y Éxito Masculino": "self-development",
        "Empoderamiento y Amor Propio Femenino": "self-development",
        "IA y Futuro": "self-development", # Default or custom if needed
        "Relaciones y Psicología Masc.": "relationships",
        "Manifestación y Espiritualidad": "self-development",
        "marketing digital": "self-development",
        "sin etiqueta": "self-development"
    }
    
    folder_name = niche_map.get(niche_name, "self-development")
    niche_dir = os.path.join(music_base_path, folder_name)
    
    if not os.path.exists(niche_dir):
        logger.warning(f"Music directory not found: {niche_dir}")
        return None
        
    music_files = [f for f in os.listdir(niche_dir) if f.endswith(('.mp3', '.wav', '.m4a'))]
    if not music_files:
        logger.warning(f"No music files found in: {niche_dir}")
        return None
        
    selected = random.choice(music_files)
    return os.path.join(niche_dir, selected)

def get_ducking_filter(words, duck_volume=0.1, fade_ms=200):
    """
    Creates an FFmpeg volume filter expression for ducking.
    """
    if not words:
        return "volume=1.0"
        
    # Simplify words to active intervals (speech periods)
    # We add a small buffer and combine overlapping intervals
    intervals = []
    for w in words:
        start = max(0, float(w['start']) - 0.1)
        end = float(w['end']) + 0.1
        if not intervals or start > intervals[-1][1]:
            intervals.append([start, end])
        else:
            intervals[-1][1] = max(intervals[-1][1], end)
            
    # Build the 'if' condition string
    # volume='if(between(t,s1,e1)+between(t,s2,e2), duck_vol, 1.0)'
    conditions = []
    for start, end in intervals:
        conditions.append(f"between(t,{start:.3f},{end:.3f})")
    
    condition_str = "+".join(conditions)
    # Adding linear ramp might be hard in a single expression without complex math
    # But 'eval=frame' with a simple 'if' is usually okay for voice.
    # Advanced: use 'threshold' or sidechain, but pulse is more reliable for transciption data.
    
    return f"volume='if({condition_str}, {duck_volume}, 1.0)':eval=frame"

def mix_audio_with_ducking(voice_path, music_path, output_path, words, bg_volume=0.4):
    """
    Mixes voice and music using FFmpeg with automatic ducking based on word timestamps.
    """
    logger.info(f"Mixing audio with ducking: {voice_path} + {music_path} -> {output_path}")
    
    # 1. Get the ducking filter expression
    duck_filter = get_ducking_filter(words, duck_volume=0.1) # 10% volume during speech
    
    # 2. Pick a random start offset for the music to avoid repetition
    # We need to know music duration first (optional but better)
    # For now, we use -stream_loop -1 to ensure it never runs out.
    
    # Construction:
    # -i voice
    # -stream_loop -1 -i music
    # [1:a] <duck_filter>, volume=<bg_volume> [bg];
    # [0:a][bg] amix=inputs=2:duration=first:dropout_transition=0 [out]
    
    # Random offset (e.g. up to 30s)
    offset = random.randint(0, 30)
    
    command = [
        "ffmpeg", "-y",
        "-i", voice_path,
        "-ss", str(offset),
        "-stream_loop", "-1", "-i", music_path,
        "-filter_complex", 
        f"[1:a]{duck_filter},volume={bg_volume}[bg];"
        f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "[a]",
        "-c:a", "pcm_s16le", # Output as WAV for Remotion
        "-ar", "44100",
        "-ac", "2",
        output_path
    ]
    
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("Audio mixing successful.")
        return True
    except Exception as e:
        logger.error(f"FFmpeg mixing failed: {str(e)}")
        return False
