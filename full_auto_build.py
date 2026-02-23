import os
import subprocess
import json
import shutil
import sys
import logging
from dotenv import load_dotenv

# Configuración de Logging (mismo archivo que backend)
LOG_FILE = "pipeline.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Path configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REMOTION_APP_DIR = os.path.join(BASE_DIR, "remotion-app")
BACKEND_SCRIPT = os.path.join(BASE_DIR, "backend_pipeline.py")

def run_step(name, command_list, cwd=None):
    logger.info(f"STEP START: {name}")
    # Quote each argument to handle paths with spaces correctly on Windows
    quoted_command = [f'"{arg}"' if " " in arg else arg for arg in command_list]
    command_str = " ".join(quoted_command)
    
    try:
        # Add FFmpeg path to current process environment
        env = os.environ.copy()
        ffmpeg_bin = r"C:\Users\MELCHOR\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
        if ffmpeg_bin not in env.get("PATH", ""):
            env["PATH"] = ffmpeg_bin + os.pathsep + env.get("PATH", "")
            
        subprocess.run(command_str, cwd=cwd, check=True, shell=True, env=env)
        logger.info(f"STEP SUCCESS: {name}")
    except subprocess.CalledProcessError as e:
        logger.error(f"STEP FAILED: {name}. Error: {e}")
        sys.exit(1)



def main():
    # 1. Load environment
    load_dotenv()
    if not os.environ.get("GEMINI_API_KEY"):
        print("Error: Se requiere GEMINI_API_KEY en el archivo .env")
        return

    # 2. Get URL from user or use default
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("Pega el link de YouTube (presiona Enter para usar el de prueba): ")
        if not url.strip():
            url = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"


    # 2.5 Clean up local and Remotion public folders
    print(">>> Limpiando archivos temporales...")
    temp_files = ["output_vertical_clip.mp4", "transcript_data.json"]
    for f in temp_files:
        # Local
        try:
            local_p = os.path.join(BASE_DIR, f)
            if os.path.exists(local_p):
                os.remove(local_p)
        except PermissionError:
            print(f"  - Advertencia: No se pudo borrar {f} (archivo en uso)")
        # Remotion public
        try:
            rem_p = os.path.join(REMOTION_APP_DIR, "public", f)
            if os.path.exists(rem_p):
                os.remove(rem_p)
                print(f"  - Borrado: remotion-app/public/{f}")
        except PermissionError:
            print(f"  - Advertencia: No se pudo borrar remotion-app/public/{f}")


    # 3. Run Backend Pipeline
    run_step("Motor de IA (Descarga, Transcripción y Análisis)", ["python", BACKEND_SCRIPT, url])


    # 4. Move assets to Remotion folder
    print(">>> Sincronizando archivos con Remotion...")
    
    # Definir rutas absolutas para evitar fallos
    transcript_src = os.path.join(BASE_DIR, "transcript_data.json")
    transcript_dest = os.path.join(REMOTION_APP_DIR, "src", "transcript_data.json")
    video_src = os.path.join(BASE_DIR, "output_vertical_clip.mp4")
    video_dest = os.path.join(REMOTION_APP_DIR, "public", "output_vertical_clip.mp4")

    # Transcript goes to src/ (for import)
    if os.path.exists(transcript_src):
        shutil.copy2(transcript_src, transcript_dest)
        print(f"  - transcript_data.json -> {transcript_dest}")
    
    # Video goes to public/ (for staticFile)
    if os.path.exists(video_src):
        shutil.copy2(video_src, video_dest)
        print(f"  - output_vertical_clip.mp4 -> {video_dest}")

    # 5. Render Video with Remotion
    print("\n>>> Iniciando Renderizado de Remotion...")
    run_step("Renderizado Final", ["npm", "run", "build"], cwd=REMOTION_APP_DIR)



    print("\n\n" + "="*40)
    print("¡PROCESO COMPLETADO!")
    print(f"Tu video final está en: {os.path.join(REMOTION_APP_DIR, 'out.mp4')}")
    print("="*40)

if __name__ == "__main__":
    main()
