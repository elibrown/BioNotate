"""Mocked browser flow; no microphone, backend, or database required.

Run from the repository root:
  python -m pip install playwright
  python -m playwright install chromium
  python -m unittest discover -s frontend/tests -p 'test_audio_e2e.py'
"""
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

FRONTEND = Path(__file__).resolve().parents[1]
FIELDS = ("counting_normal", "counting_fast", "vowel_a", "vowel_e", "vowel_o")
MICROPHONE = """
window.__stoppedTracks = 0;
navigator.mediaDevices.getUserMedia = async () => ({
  getTracks: () => [{stop: () => window.__stoppedTracks++}]
});
window.MediaRecorder = class {
  static isTypeSupported() { return true; }
  constructor() { this.state = "inactive"; }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    this.ondataavailable({data: new Blob(["mock recording"], {type:"audio/webm"})});
    this.onstop();
  }
};
"""


class AudioBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.route("http://localhost:8000/**", self.serve)
        self.page.add_init_script(MICROPHONE)
        self.page.clock.install()

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])

    def serve(self, route):
        path = route.request.url.split("8000", 1)[1].split("?", 1)[0]
        if path == "/api/dashboard":
            route.fulfill(json={"mode": "live", "crew": [{"id": "A-01", "name": "Alex Morgan"}]})
            return
        files = {
            "/audio": ("audio.html", "text/html"),
            "/static/audio.js": ("audio.js", "application/javascript"),
            "/static/dashboard.css": ("dashboard.css", "text/css"),
        }
        if path not in files:
            route.abort()
            return
        name, content_type = files[path]
        route.fulfill(body=(FRONTEND / name).read_text(), content_type=content_type)

    def test_five_recordings_submit_expected_multipart_fields(self):
        requests = []

        def submit(route):
            requests.append(route.request)
            route.fulfill(json={"result": {"status": "ok", "log_message": "Mock analysis completed."}})

        self.page.route("**/api/audio", submit)
        self.page.goto("http://localhost:8000/audio")
        for index in range(5):
            expect(self.page.locator("#audio-progress")).to_have_text(f"Step {index + 1} of 5")
            self.page.locator("#audio-record").click()
            expect(self.page.locator("#audio-record")).to_have_text("Stop recording")
            self.page.clock.fast_forward(6000)
            self.page.locator("#audio-record").click()
            expect(self.page.locator("#audio-record")).to_have_text("Start recording")
            expect(self.page.locator("#audio-retry")).to_be_enabled()
            if index < 4:
                self.page.locator("#audio-next").click()
        expect(self.page.locator("#audio-completed")).to_have_text("5 of 5 completed")
        expect(self.page.locator("#audio-send")).to_be_enabled()
        self.page.locator("#audio-send").click()
        expect(self.page.locator("#audio-astronaut")).to_be_focused()
        expect(self.page.locator("#audio-submit-help")).to_contain_text("Select an astronaut")
        self.assertEqual(len(requests), 0)
        self.page.locator("#audio-astronaut").select_option("A-01")
        self.page.locator("#audio-send").click()
        expect(self.page.locator("#audio-status")).to_have_text("All five recordings were analyzed successfully.")
        expect(self.page.locator("#audio-result")).to_be_visible()
        self.assertEqual(len(requests), 1)
        body = requests[0].post_data_buffer.decode()
        for field in (*FIELDS, "astronaut_id"):
            self.assertIn(f'name="{field}"', body)
        self.assertIn("A-01", body)
        self.assertEqual(self.page.evaluate("window.__stoppedTracks"), 5)

    def test_pending_microphone_permission_recovers_and_stops_late_stream(self):
        self.page.add_init_script("""
navigator.mediaDevices.getUserMedia = () => new Promise(resolve => {
  window.__grantMic = () => resolve({
    getTracks: () => [{stop: () => window.__stoppedTracks++}]
  });
});
""")
        self.page.goto("http://localhost:8000/audio")
        self.page.locator("#audio-record").click()
        expect(self.page.locator("#audio-status")).to_contain_text("Waiting for microphone permission")
        self.page.clock.fast_forward(21000)
        expect(self.page.locator("#audio-record")).to_be_enabled()
        expect(self.page.locator("#audio-status")).to_contain_text("permission is still pending")
        self.page.evaluate("window.__grantMic()")
        expect(self.page.locator("#audio-record")).to_be_enabled()
        self.assertEqual(self.page.evaluate("window.__stoppedTracks"), 1)


if __name__ == "__main__":
    unittest.main()
