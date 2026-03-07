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
    # We add a generous buffer (1.5s) to merge close words.
    # Viral shorts rarely have >3s pauses, so this essentially creates one continuous ducking block.
    intervals = []
    for w in words:
        start = max(0, float(w['start']) - 1.5)
        end = float(w['end']) + 1.5
        if not intervals or start > intervals[-1][1]:
            intervals.append([start, end])
        else:
            intervals[-1][1] = max(intervals[-1][1], end)
            
    # Safeguard against FFmpeg expression complexity limit (returns AVERROR(EINVAL))
    # FFmpeg AVExpr crashes if the syntax tree is too large. 10 intervals = safe.
    if len(intervals) > 10:
        logger.warning(f"Audio has {len(intervals)} intervals. Condensing to 1 global ducking block to prevent FFmpeg crash.")
        global_start = intervals[0][0]
        global_end = intervals[-1][1]
        intervals = [[global_start, global_end]]

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

def mix_audio_with_ducking(voice_path, music_path, output_path, words=None, bg_volume=0.06):
    """
    Mixes voice and music using FFmpeg with a CONSTANT, homogeneous background level.
    Removed dynamic ducking as per user request to mimic standard CapCut editing.
    Uses -filter_complex_script (temp file) to avoid Windows shell quoting bugs.
    """
    import tempfile
    logger.info(f"Mixing audio with static background volume: {voice_path} + {music_path} -> {output_path}")

    offset = random.randint(0, 30)

    # Simple static volume filter for the background music track
    filter_complex = (
        f"[1:a]volume={bg_volume}[bg];"
        f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]"
    )

    # Write filter to a temp file — bypasses ALL shell quoting issues
    filter_script_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tmp:
            tmp.write(filter_complex)
            filter_script_path = tmp.name
    except Exception as e:
        logger.error(f"Failed to write FFmpeg filter script: {e}")
        return False

    try:
        command = [
            "ffmpeg", "-y",
            "-i", voice_path,
            "-ss", str(offset), "-stream_loop", "-1", "-i", music_path,
            "-filter_complex_script", filter_script_path,
            "-map", "[a]",
            "-c:a", "pcm_s16le",
            "-ar", "44100",
            "-ac", "2",
            output_path
        ]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("Audio mixing successful.")
        return True
    except Exception as e:
        logger.error(f"FFmpeg mixing failed: {str(e)}")
        return False
    finally:
        if filter_script_path:
            try:
                os.unlink(filter_script_path)
            except Exception:
                pass

