#!/usr/bin/env python3
"""CLI to register faces into the JARVIS face database.

Usage:
    # Register from an existing photo
    python scripts/register_face.py --name "John" --image path/to/photo.jpg

    # Register from a webcam snapshot
    python scripts/register_face.py --name "John" --webcam

    # Bulk-register all images in faces/<name>/*.jpg
    python scripts/register_face.py --scan

    # List registered identities
    python scripts/register_face.py --list

    # Remove an identity
    python scripts/register_face.py --remove "John"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.tools.face_recognition import FaceRecognizer


def capture_webcam(name: str, recognizer: FaceRecognizer, camera_index: int = 0):
    import cv2

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"Error: cannot open camera {camera_index}")
        return

    print("Press SPACE to capture, Q to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imshow("Register Face - Press SPACE", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord(" "):
            save_dir = recognizer.faces_dir / name
            save_dir.mkdir(parents=True, exist_ok=True)
            existing = list(save_dir.glob("*.jpg"))
            filename = save_dir / f"{len(existing):03d}.jpg"
            cv2.imwrite(str(filename), frame)
            print(f"Saved snapshot to {filename}")
            if recognizer.register_face(name, filename):
                print(f"Registered face for '{name}'")
            else:
                print("No face detected in snapshot, try again.")
        elif key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="Register faces for JARVIS recognition")
    parser.add_argument("--name", help="Name of the person to register")
    parser.add_argument("--image", help="Path to a photo to register")
    parser.add_argument("--webcam", action="store_true", help="Capture from webcam")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default 0)")
    parser.add_argument("--scan", action="store_true", help="Bulk-register from faces/ directory")
    parser.add_argument("--list", action="store_true", help="List registered identities")
    parser.add_argument("--remove", help="Remove a registered identity by name")
    parser.add_argument("--threshold", type=float, default=0.55, help="Match threshold")
    args = parser.parse_args()

    recognizer = FaceRecognizer(threshold=args.threshold)

    if args.list:
        identities = recognizer.list_identities()
        if not identities:
            print("No registered faces.")
        else:
            for name, count in sorted(identities.items()):
                print(f"  {name}: {count} embedding(s)")
        return

    if args.remove:
        if recognizer.remove_identity(args.remove):
            print(f"Removed '{args.remove}'")
        else:
            print(f"'{args.remove}' not found in database")
        return

    if args.scan:
        results = recognizer.register_all()
        if not results:
            print(f"No face directories found in {recognizer.faces_dir}/")
            print(f"Create directories like {recognizer.faces_dir}/John/ with .jpg files inside.")
        else:
            for name, count in results.items():
                print(f"  {name}: {count} face(s) registered")
        return

    if args.webcam:
        if not args.name:
            parser.error("--webcam requires --name")
        capture_webcam(args.name, recognizer, args.camera)
        return

    if args.image:
        if not args.name:
            parser.error("--image requires --name")
        if recognizer.register_face(args.name, args.image):
            print(f"Registered face for '{args.name}' from {args.image}")
        else:
            print(f"No face detected in {args.image}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
