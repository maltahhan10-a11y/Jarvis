"""Facial recognition using InsightFace (buffalo_l) with a local face database."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger("jarvis.tools.face_recognition")

FACES_DIR = Path("faces")
DB_PATH = Path("data/face_db.json")
DEFAULT_THRESHOLD = 0.55


@dataclass
class FaceResult:
    name: str | None
    confidence: float
    estimated_age: int | None
    estimated_gender: str | None
    bbox: tuple[int, int, int, int]


class FaceRecognizer:
    """Identifies faces against a local embedding database.

    Usage:
        recognizer = FaceRecognizer()
        results = recognizer.identify(frame)
    """

    def __init__(
        self,
        faces_dir: str | Path = FACES_DIR,
        db_path: str | Path = DB_PATH,
        threshold: float = DEFAULT_THRESHOLD,
        providers: list[str] | None = None,
    ):
        self.faces_dir = Path(faces_dir)
        self.db_path = Path(db_path)
        self.threshold = threshold
        self._providers = providers or self._detect_providers()
        self._app = None
        self._db: dict[str, list[list[float]]] = {}
        self._load_db()

    def _detect_providers(self) -> list[str]:
        try:
            import onnxruntime as ort
            if "CUDAExecutionProvider" in ort.get_available_providers():
                return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        except ImportError:
            pass
        return ["CPUExecutionProvider"]

    def _get_app(self):
        if self._app is None:
            from insightface.app import FaceAnalysis
            self._app = FaceAnalysis(
                name="buffalo_l",
                providers=self._providers,
            )
            self._app.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("InsightFace buffalo_l loaded (providers=%s)", self._providers)
        return self._app

    def _load_db(self):
        if self.db_path.exists():
            with open(self.db_path) as f:
                self._db = json.load(f)
            logger.info("Loaded face DB with %d identities", len(self._db))

    def _save_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.db_path, "w") as f:
            json.dump(self._db, f, indent=2)

    def register_face(self, name: str, image_path: str | Path) -> bool:
        """Embed a reference photo and add it to the database.

        Returns True on success, False if no face was detected.
        """
        img = cv2.imread(str(image_path))
        if img is None:
            logger.error("Cannot read image: %s", image_path)
            return False

        faces = self._get_app().get(img)
        if not faces:
            logger.warning("No face detected in %s", image_path)
            return False

        embedding = faces[0].normed_embedding.tolist()
        self._db.setdefault(name, []).append(embedding)
        self._save_db()
        logger.info("Registered face for '%s' from %s (total embeddings: %d)",
                     name, image_path, len(self._db[name]))
        return True

    def register_all(self) -> dict[str, int]:
        """Scan faces_dir and register all images. Returns {name: count}."""
        registered: dict[str, int] = {}
        if not self.faces_dir.exists():
            logger.warning("Faces directory not found: %s", self.faces_dir)
            return registered

        for person_dir in sorted(self.faces_dir.iterdir()):
            if not person_dir.is_dir():
                continue
            name = person_dir.name
            count = 0
            for img_path in sorted(person_dir.iterdir()):
                if img_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                    if self.register_face(name, img_path):
                        count += 1
            registered[name] = count

        logger.info("Bulk registration complete: %s", registered)
        return registered

    def identify(self, frame: np.ndarray) -> list[FaceResult]:
        """Identify all faces in a BGR frame.

        Returns a list of FaceResult for each detected face.
        Unknown faces have name=None.
        """
        try:
            faces = self._get_app().get(frame)
        except Exception:
            logger.exception("InsightFace inference failed")
            return []

        results = []
        for face in faces:
            bbox = tuple(int(v) for v in face.bbox[:4])
            age = int(face.age) if hasattr(face, "age") and face.age is not None else None
            gender = None
            if hasattr(face, "gender") and face.gender is not None:
                gender = "male" if int(face.gender) == 1 else "female"

            best_name = None
            best_score = -1.0

            if face.normed_embedding is not None and self._db:
                query = np.array(face.normed_embedding)
                for name, embeddings in self._db.items():
                    for emb in embeddings:
                        score = float(np.dot(query, np.array(emb)))
                        if score > best_score:
                            best_score = score
                            best_name = name

            matched_name = best_name if best_score >= self.threshold else None
            confidence = max(best_score, 0.0) if best_score > 0 else 0.0

            results.append(FaceResult(
                name=matched_name,
                confidence=round(confidence, 4),
                estimated_age=age,
                estimated_gender=gender,
                bbox=bbox,
            ))

        return results

    def identify_from_camera(self, camera_index: int = 0) -> list[FaceResult]:
        """Capture a single frame from a camera and identify faces."""
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            logger.error("Cannot open camera %d", camera_index)
            return []
        try:
            ret, frame = cap.read()
            if not ret:
                logger.error("Failed to capture frame from camera %d", camera_index)
                return []
            return self.identify(frame)
        finally:
            cap.release()

    def list_identities(self) -> dict[str, int]:
        """Return {name: embedding_count} for all registered identities."""
        return {name: len(embs) for name, embs in self._db.items()}

    def remove_identity(self, name: str) -> bool:
        """Remove a person from the database."""
        if name in self._db:
            del self._db[name]
            self._save_db()
            return True
        return False
