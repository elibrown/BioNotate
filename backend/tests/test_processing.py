import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app.routers import video

from app.processing import AudioProcessor, MetricsProcessor, ProcessorFactory, VideoProcessor


class ProcessingTests(unittest.TestCase):
    def test_selects_processor(self):
        for data_type, expected in [("video", VideoProcessor), ("audio", AudioProcessor),
                                    ("metrics", MetricsProcessor)]:
            with self.subTest(data_type=data_type):
                self.assertIsInstance(ProcessorFactory().get_processor(data_type), expected)

    def test_unknown_type(self):
        with self.assertRaises(ValueError):
            ProcessorFactory().get_processor("unknown")

    def test_skeleton_passes_data_through(self):
        data = {"example": 1}
        for data_type in ("video", "audio", "metrics"):
            with self.subTest(data_type=data_type):
                self.assertIs(ProcessorFactory().get_processor(data_type).process(data), data)

    def test_upload_uses_video_processor(self):
        with TemporaryDirectory() as directory:
            prepared = Path(directory) / "prepared.mp4"
            prepared.write_bytes(b"prepared fixture")
            with patch.object(video, "UPLOAD_DIR", Path(directory)), patch.object(
                VideoProcessor, "process", return_value=prepared
            ) as process, patch.object(video, "run_model", return_value={"stub": True}) as model:
                response = TestClient(app).post(
                    "/api/video", files={"file": ("clip.mp4", b"upload fixture", "video/mp4")}
                )
                self.assertEqual(response.status_code, 200)
                saved = Path(directory) / response.json()["saved_as"]
                self.assertEqual(saved.read_bytes(), b"upload fixture")
                process.assert_called_once_with(saved)
                model.assert_called_once_with(prepared)
                self.assertEqual(response.json()["result"], {"stub": True})


if __name__ == "__main__":
    unittest.main()
