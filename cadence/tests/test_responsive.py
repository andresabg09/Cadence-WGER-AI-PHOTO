"""A slow Gemini call must never freeze the rest of the server (it once did: every page and script timed out behind it)."""

import threading
import time

from app import main

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class SlowVision:
    def __init__(self, seconds: float):
        self.seconds = seconds

    def identify_components(self, image_bytes, mime):
        time.sleep(self.seconds)
        return []

    def identify_from_audio(self, data, mime):
        time.sleep(self.seconds)
        return []

    def transcribe(self, data, mime):
        time.sleep(self.seconds)
        return ""


def _others_answer_while(monkeypatch, call):
    """Runs the real server (uvicorn, one event loop like production) and times /health while one request sits inside Gemini."""
    import socket

    import httpx
    import uvicorn

    from app import coach

    monkeypatch.setattr(main, "get_vision_client", lambda: SlowVision(2.0))
    monkeypatch.setattr(coach, "_client", lambda: SlowVision(2.0))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error"))
    runner = threading.Thread(target=server.run, daemon=True)
    runner.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        slow = threading.Thread(target=lambda: call(httpx.Client(base_url=base, timeout=10)), daemon=True)
        slow.start()
        time.sleep(0.5)  # the slow request is now inside Gemini
        started = time.monotonic()
        assert httpx.get(f"{base}/health", timeout=10).status_code == 200
        took = time.monotonic() - started
        slow.join(6)
        return took
    finally:
        server.should_exit = True
        runner.join(5)


def test_a_slow_photo_analysis_does_not_block_other_requests(monkeypatch):
    took = _others_answer_while(monkeypatch, lambda h: h.post("/api/analyze", files={"image": ("a.png", PNG, "image/png")}))
    assert took < 0.8, f"the server was frozen for {took:.1f}s behind a slow Gemini call"


def test_a_slow_voice_log_does_not_block_other_requests(monkeypatch):
    took = _others_answer_while(monkeypatch, lambda h: h.post("/api/voice", files={"audio": ("a.wav", b"RIFF" + b"0" * 64, "audio/wav")}))
    assert took < 0.8


def test_a_slow_dictation_does_not_block_other_requests(monkeypatch):
    took = _others_answer_while(monkeypatch, lambda h: h.post("/api/transcribe", files={"audio": ("a.wav", b"RIFF" + b"0" * 64, "audio/wav")}))
    assert took < 0.8
