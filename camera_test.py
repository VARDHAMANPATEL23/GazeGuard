import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import time
import sys

def main():
    print("Initializing MediaPipe Face Landmarker...")
    
    base_options = python.BaseOptions(model_asset_path='face_landmarker.task')
    options = vision.FaceLandmarkerOptions(
        base_options=base_options,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
        num_faces=1)
    
    try:
        detector = vision.FaceLandmarker.create_from_options(options)
    except Exception as e:
        print(f"Failed to load FaceLandmarker: {e}")
        print("Make sure 'face_landmarker.task' is downloaded in the project root.")
        sys.exit(1)

    print("Opening camera (device 0)...")
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: Could not open camera.")
        sys.exit(1)

    print("Camera opened successfully. Press 'q' to exit.")
    
    # Let the camera warm up
    time.sleep(1)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame.")
                break

            # Flip frame horizontally for a more natural mirror view
            frame = cv2.flip(frame, 1)
            
            # Convert the BGR image to RGB before processing
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Process with MediaPipe Tasks API
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            detection_result = detector.detect(mp_image)

            h, w, _ = frame.shape

            if detection_result.face_landmarks:
                for face_landmarks in detection_result.face_landmarks:
                    # Iris landmarks: 468 (Left Iris Center), 473 (Right Iris Center)
                    if len(face_landmarks) > 473:
                        left_iris = face_landmarks[468]
                        right_iris = face_landmarks[473]
                        
                        lx, ly = int(left_iris.x * w), int(left_iris.y * h)
                        rx, ry = int(right_iris.x * w), int(right_iris.y * h)
                        
                        # Draw green circles on the irises
                        cv2.circle(frame, (lx, ly), 4, (0, 255, 0), -1)
                        cv2.circle(frame, (rx, ry), 4, (0, 255, 0), -1)
                        
                        cv2.putText(frame, f"Left Iris: ({lx}, {ly})", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        cv2.putText(frame, f"Right Iris: ({rx}, {ry})", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    else:
                        cv2.putText(frame, "Iris landmarks not available", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            else:
                cv2.putText(frame, "No face detected", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.imshow("GazeGuard - Camera Test", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        detector.close()
        print("Camera closed.")

if __name__ == "__main__":
    main()
