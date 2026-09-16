"""
Phase 3 smoke test — run this after calibration to verify get_gaze_point() works.
Press Ctrl+C to stop.
"""
import time
import sys
from core.gaze_engine import GazeEngine

def main():
    print("Starting GazeEngine... (Ctrl+C to stop)")
    engine = GazeEngine(smoothing_level="medium")
    engine.start()

    time.sleep(2)  # Let pipeline warm up

    print("Streaming gaze coordinates:")
    try:
        while True:
            pt = engine.get_gaze_point()
            multi = engine.is_multi_face()
            faces = engine.face_count()

            if pt:
                label = "MULTI-FACE ALERT" if multi else f"Gaze: ({pt[0]:4d}, {pt[1]:4d})"
                print(f"\r{label}  | Faces: {faces}   ", end="", flush=True)
            else:
                print(f"\r[No face detected]                  ", end="", flush=True)
            
            time.sleep(1/30)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        engine.stop()
        print("Done.")

if __name__ == "__main__":
    main()
