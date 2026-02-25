import os
import cv2
import mediapipe as mp
import json

def diagnose_faces(image_path, output_path, log_file):
    with open(log_file, "a") as f:
        f.write(f"\n--- Analyzing {image_path} ---\n")
        
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blaze_face_short_range.tflite")
        
        BaseOptions = mp.tasks.BaseOptions
        FaceDetector = mp.tasks.vision.FaceDetector
        FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions
        
        options = FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            min_detection_confidence=0.1
        )
        
        with FaceDetector.create_from_options(options) as detector:
            image = cv2.imread(image_path)
            if image is None:
                f.write(f"Error: Could not load {image_path}\n")
                return
                
            img_h, img_w, _ = image.shape
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
            
            results = detector.detect(mp_image)
            
            if not results.detections:
                f.write("No faces detected.\n")
            else:
                f.write(f"Detected {len(results.detections)} face(s):\n")
                for i, detection in enumerate(results.detections):
                    bbox = detection.bounding_box
                    score = detection.categories[0].score
                    nx = bbox.origin_x / img_w
                    ny = bbox.origin_y / img_h
                    nw = bbox.width / img_w
                    nh = bbox.height / img_h
                    cx = (bbox.origin_x + bbox.width / 2) / img_w
                    
                    f.write(f"[{i}] Confidence: {score:.4f}, CenterX: {cx:.4f}, BBox: x={nx:.3f}, y={ny:.3f}, w={nw:.3f}, h={nh:.3f}\n")
                    
                    start_point = (int(bbox.origin_x), int(bbox.origin_y))
                    end_point = (int(bbox.origin_x + bbox.width), int(bbox.origin_y + bbox.height))
                    cv2.rectangle(image, start_point, end_point, (0, 255, 0), 3)
                    cv2.putText(image, f"F{i}: {score:.2f}", (start_point[0], start_point[1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

            cv2.imwrite(output_path, image)
            f.write(f"Debug image saved to {output_path}\n")

if __name__ == "__main__":
    LOG = "face_diag.log"
    if os.path.exists(LOG): os.remove(LOG)
    diagnose_faces("debug_frame_4s.jpg", "result_4s.jpg", LOG)
    diagnose_faces("debug_frame_20s.jpg", "result_20s.jpg", LOG)
