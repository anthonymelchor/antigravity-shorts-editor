import os
import cv2
import mediapipe as mp
import subprocess

def extract_frame(video_path, time_in_seconds, output_path):
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

def troubleshoot_framing(image_path, log_file):
    with open(log_file, "a", encoding="utf-8") as f_log:
        f_log.write(f"\nTroubleshooting: {image_path}\n")
        face_model_path = "blaze_face_short_range.tflite"
        obj_model_path = "efficientdet_lite0.tflite"
        
        face_options = mp.tasks.vision.FaceDetectorOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=face_model_path),
            min_detection_confidence=0.3
        )
        
        obj_options = mp.tasks.vision.ObjectDetectorOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=obj_model_path),
            score_threshold=0.3
        )
        
        image = cv2.imread(image_path)
        h, w, _ = image.shape
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
        
        with mp.tasks.vision.FaceDetector.create_from_options(face_options) as face_detector, \
             mp.tasks.vision.ObjectDetector.create_from_options(obj_options) as obj_detector:
            
            faces = face_detector.detect(mp_image).detections
            objects = obj_detector.detect(mp_image).detections
            people = [o for o in objects if o.categories[0].category_name == 'person']
            
            f_log.write(f"Detected {len(faces)} faces.\n")
            for i, f in enumerate(faces):
                f_log.write(f"  Face {i}: confidence {f.categories[0].score:.2f}, centerX {(f.bounding_box.origin_x + f.bounding_box.width/2)/w:.2f}\n")
                
            f_log.write(f"Detected {len(people)} people.\n")
            for i, p in enumerate(people):
                f_log.write(f"  Person {i}: confidence {p.categories[0].score:.2f}, centerX {(p.bounding_box.origin_x + p.bounding_box.width/2)/w:.2f}\n")

            layout = "single"
            if len(faces) >= 2:
                layout = "split"
                f_log.write("Decision: split (via faces >= 2)\n")
            elif len(faces) == 1:
                layout = "single"
                f_log.write("Decision: single (via faces == 1)\n")
            elif len(people) >= 1:
                if len(people) >= 2:
                    layout = "split"
                    f_log.write("Decision: split (via people >= 2)\n")
                else:
                    layout = "single"
                    f_log.write("Decision: single (via people == 1)\n")
            
            f_log.write(f"FINAL DECISION: {layout}\n")

if __name__ == "__main__":
    VIDEO = "input_1772158425.mp4"
    CLIP_START = 424.1
    TIMESTAMPS = [0.0, 4.5, 8.6, 12.2, 19.6]
    LOG = "diag_clip7.log"
    
    if os.path.exists(LOG): os.remove(LOG)
    
    if os.path.exists(VIDEO):
        for ts in TIMESTAMPS:
            IMAGE = f"troubleshoot_clip7_{ts}s.jpg"
            with open(LOG, "a", encoding="utf-8") as f_log:
                f_log.write(f"\n--- Checking at {ts}s (Global: {CLIP_START + ts}s) ---\n")
            extract_frame(VIDEO, CLIP_START + ts, IMAGE)
            troubleshoot_framing(IMAGE, LOG)
    else:
        print(f"ERROR: {VIDEO} not found.")
