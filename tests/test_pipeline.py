import asyncio
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from polimi_lectures.core import Catalog, DownloadError, download_mp4, playlist_mp4, public_recording_url, slug, webex_id
from polimi_lectures.cli import download_hls, make_client


RID = "0123456789abcdef0123456789abcdef"
URL = "https://politecnicomilano.webex.com/recordingservice/sites/politecnicomilano/recording/playback/" + RID


class CatalogTests(unittest.TestCase):
    def test_identity_and_private_metadata(self):
        self.assertEqual(webex_id(URL + "?accessToken=private"), RID)
        self.assertEqual(webex_id("https://politecnicomilano.webex.com/ldr.php?RCID=" + RID), RID)
        self.assertIsNone(webex_id("https://webex.com.evil.example/recording/" + RID))
        self.assertIsNone(webex_id("https://evilwebex.com/recording/" + RID))
        self.assertNotIn("accessToken", public_recording_url(URL + "?accessToken=private"))
        self.assertNotIn("/", slug("../../un corso: 1"))

    def test_catalog_is_incremental_and_path_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(directory)
            self.assertTrue(catalog.add("Parallel Computing", URL, "Prima lezione"))
            row = catalog.rows()[0]
            path = catalog.folder(row).relative_to(directory)
            catalog.update(row, "complete", path)
            self.assertFalse(catalog.add("Parallel Computing", URL + "?token=new", "Titolo aggiornato", "2026-10-14"))
            rows = catalog.rows()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "complete")
            self.assertEqual(catalog.folder(rows[0]).relative_to(directory), path)
            self.assertEqual(rows[0]["date"], "2026-10-14")
            self.assertTrue(catalog.add("Altro corso", URL))
            catalog.db.close()

    def test_playlist_does_not_mistake_init_segment_for_full_video(self):
        base = "https://cdn.webex.com/media/hls-4.m3u8?token=private"
        playlist = '#EXTM3U\n#EXT-X-MAP:URI="lesson.mp4",BYTERANGE="100@0"\n#EXTINF:10,\n#EXT-X-BYTERANGE:1000@100\nlesson.mp4\n'
        self.assertEqual(playlist_mp4(playlist, base), "https://cdn.webex.com/media/lesson.mp4?token=private")
        self.assertIsNone(playlist_mp4(playlist.replace("\nlesson.mp4", "\nsegment1.m4s"), base))
        self.assertIsNone(playlist_mp4("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100\nchild.m3u8", base))

    def test_cookies_are_scoped(self):
        cookie = {"name": "ticket", "value": "secret", "domain": ".webex.com", "path": "/", "secure": True}
        with make_client([cookie], "Agent", URL + "?token=secret") as client:
            webex = client.build_request("GET", "https://cdn.webex.com/media/file.mp4")
            outside = client.build_request("GET", "https://other.example/file.mp4")
            self.assertIn("ticket=secret", webex.headers.get("cookie", ""))
            self.assertNotIn("cookie", outside.headers)
            self.assertNotIn("token", webex.headers["referer"])


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise unittest.SkipTest("FFmpeg non installato")
        cls.directory = tempfile.TemporaryDirectory()
        fixture = Path(cls.directory.name) / "fixture.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "color=c=black:s=160x120:r=10", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
                        "-t", "1", "-c:v", "mpeg4", "-c:a", "aac", str(fixture)], check=True, timeout=60)
        cls.payload = fixture.read_bytes()
        hls_folder = Path(cls.directory.name) / "hls"
        hls_folder.mkdir()
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(fixture),
                        "-c:v", "libx264", "-c:a", "aac", "-hls_time", "1", "-hls_list_size", "0",
                        str(hls_folder / "index.m3u8")], check=True, timeout=60)
        cls.hls = {"/hls/" + p.name: p.read_bytes() for p in hls_folder.iterdir()}
        cls.requests = []
        parent = cls

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                parent.requests.append(dict(self.headers))
                if self.path in parent.hls:
                    content = parent.hls[self.path]
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                if self.path == "/login":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<html>Login</html>")
                    return
                payload = parent.payload
                offset = 0
                status = 200
                if self.headers.get("Range") and self.headers.get("If-Range") == '"v1"':
                    offset = int(self.headers["Range"].split("=")[1].split("-")[0])
                    status = 206
                self.send_response(status)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("ETag", '"v1"')
                self.send_header("Content-Length", str(len(payload) - offset))
                if status == 206:
                    self.send_header("Content-Range", "bytes %d-%d/%d" % (offset, len(payload) - 1, len(payload)))
                self.end_headers()
                if self.path == "/truncated":
                    self.wfile.write(payload[: len(payload) // 2])
                    self.close_connection = True
                else:
                    self.wfile.write(payload[offset:])

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.directory.cleanup()

    def test_full_download_and_media_validation(self):
        with tempfile.TemporaryDirectory() as directory, httpx.Client() as client:
            target = Path(directory) / "video.mp4"
            details = download_mp4(client, self.base + "/video", target)
            self.assertEqual(target.read_bytes(), self.payload)
            self.assertGreater(details["duration_seconds"], 0)
            self.assertIn("audio", details["streams"])

    def test_resume_uses_valid_range_and_does_not_duplicate_bytes(self):
        with tempfile.TemporaryDirectory() as directory, httpx.Client() as client:
            target = Path(directory) / "video.mp4"
            partial = target.with_suffix(".mp4.part")
            partial.write_bytes(self.payload[:100])
            partial.with_suffix(".json").write_text(json.dumps({"validator": '"v1"'}))
            download_mp4(client, self.base + "/video", target)
            self.assertEqual(target.read_bytes(), self.payload)
            self.assertEqual(self.requests[-1].get("Range"), "bytes=100-")
            self.assertFalse(partial.exists())

    def test_changed_version_restarts_instead_of_appending(self):
        with tempfile.TemporaryDirectory() as directory, httpx.Client() as client:
            target = Path(directory) / "video.mp4"
            partial = target.with_suffix(".mp4.part")
            partial.write_bytes(b"old incompatible version")
            partial.with_suffix(".json").write_text(json.dumps({"validator": '"old"'}))
            download_mp4(client, self.base + "/video", target)
            self.assertEqual(target.read_bytes(), self.payload)

    def test_truncated_response_never_marks_file_complete(self):
        with tempfile.TemporaryDirectory() as directory, httpx.Client() as client:
            target = Path(directory) / "video.mp4"
            with self.assertRaises((DownloadError, httpx.HTTPError)):
                download_mp4(client, self.base + "/truncated", target)
            self.assertFalse(target.exists())
            self.assertTrue(target.with_suffix(".mp4.part").exists())

    def test_login_page_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, httpx.Client() as client:
            target = Path(directory) / "video.mp4"
            with self.assertRaises(DownloadError):
                download_mp4(client, self.base + "/login", target)
            self.assertFalse(target.exists())

    def test_hls_segments_are_downloaded_and_merged_with_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "video.mp4"
            details = asyncio.run(download_hls(self.base + "/hls/index.m3u8", target, [], "Test", self.base))
            self.assertTrue(target.exists())
            self.assertIn("audio", details["streams"])
            self.assertIn("video", details["streams"])


if __name__ == "__main__":
    unittest.main()
