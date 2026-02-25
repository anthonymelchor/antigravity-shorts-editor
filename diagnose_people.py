import os
import cv2
import mediapipe as mp
import json

def diagnose_people(image_path, output_path, log_file):
    with open(log_file, "a") as f:
        f.write(f"\n--- Analyzing People in {image_path} ---\n")
        
        # Model: efficientdet_lite0 for object detection (includes 'person')
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "efficientdet_lite0.tflite")
        
        if not os.path.exists(model_path):
            import urllib.request
            f.write("Downloading MediaPipe Object Detection Model...\n")
            urllib.request.urlretrieve("https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float16/1/efficientdet_lite0.tflite", model_path)

        BaseOptions = mp.tasks.BaseOptions
        ObjectDetector = mp.tasks.vision.ObjectDetector
        ObjectDetectorOptions = mp.tasks.vision.ObjectDetectorOptions
        
        options = ObjectDetectorOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            score_threshold=0.2 # Lower to see potential detections
        )
        
        with ObjectDetector.create_from_options(options) as detector:
            image = cv2.imread(image_path)
            if image is None:
                f.write(f"Error: Could not load {image_path}\n")
                return
                
            img_h, img_w, _ = image.shape
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
            
            results = detector.detect(mp_image)
            
            people = [d for d in results.detections if d.categories[0].category_name == 'person']
            
            if not people:
                f.write("No people detected.\n")
            else:
                f.write(f"Detected {len(people)} person(s):\n")
                for i, person in enumerate(people):
                    bbox = person.bounding_box
                    score = person.categories[0].score
                    
                    nx = bbox.origin_x / img_w
                    ny = bbox.origin_y / img_h
                    nw = bbox.width / img_w
                    nh = bbox.height / img_h
                    cx = (bbox.origin_x + bbox.width / 2) / img_w
                    
                    f.write(f"[{i}] Confidence: {score:.4f}, CenterX: {cx:.4f}, BBox: x={nx:.3f}, y={ny:.3f}, w={nw:.3f}, h={nh:.3f}\n")
                    
                    # Draw
                    start_point = (int(bbox.origin_x), int(bbox.origin_y))
                    end_point = (int(bbox.origin_x + bbox.width), int(bbox.origin_y + bbox.height))
                    cv2.rectangle(image, start_point, end_point, (255, 0, 0), 4)
                    cv2.putText(image, f"PERSON {i}: {score:.2f}", (start_point[0], start_point[1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)

            cv2.imwrite(output_path, image)
            f.write(f"Debug image saved to {output_path}\n")

if __name__ == "__main__":
    LOG = "people_diag.log"
    if os.path.exists(LOG): os.remove(LOG)
    diagnose_people("debug_frame_4s.jpg", "result_people_4s.jpg", LOG)
    diagnose_people("debug_frame_20s.jpg", "result_people_20s.jpg", LOG)
