import json
import re
import sqlite3
import subprocess
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit


class DownloadError(Exception):
    pass


def slug(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip(".-_")[:100] or "lezione"


def webex_id(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host.endswith(".webex.com"):
        return None
    ids = re.findall(r"(?<![a-fA-F0-9])[a-fA-F0-9]{32}(?![a-fA-F0-9])", parsed.path)
    if ids:
        return ids[-1].lower()
    for key, values in parse_qs(parsed.query).items():
        if key.lower() == "rcid" and re.fullmatch(r"[a-fA-F0-9]{32}", values[0]):
            return values[0].lower()
    return None


def public_recording_url(url):
    """Solo riferimento pubblico nei metadata: il link di accesso resta nel DB privato."""
    parsed = urlsplit(url)
    if "ldr.php" in parsed.path:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "RCID=" + webex_id(url), ""))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def playlist_mp4(text, playlist_url):
    """Solo playlist byte-range che referenziano un unico MP4, non init + segmenti."""
    if not text.lstrip().startswith("#EXTM3U"):
        return None
    if "#EXT-X-STREAM-INF" in text or "#EXT-X-KEY" in text:
        return None
    uris = re.findall(r'#EXT-X-MAP:.*?URI="([^"]+)"', text)
    media = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if not media or "#EXT-X-BYTERANGE" not in text:
        return None
    refs = {urljoin(playlist_url, uri) for uri in uris + media}
    if len(refs) != 1:
        return None
    result = refs.pop()
    if not urlsplit(result).path.lower().endswith(".mp4"):
        return None
    # Alcuni CDN richiedono gli stessi parametri firmati della playlist.
    source, target = urlsplit(playlist_url), urlsplit(result)
    if not target.query and source.query and target.netloc == source.netloc:
        result = urlunsplit((target.scheme, target.netloc, target.path, source.query, ""))
    return result


def media_candidates(value):
    """Estrae solo campi conosciuti, senza salvare risposte/API contenenti token."""
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("fallbackPlaySrc", "hlsURL", "downloadUrl", "downloadURL") and isinstance(child, str):
                if child.startswith("https://"):
                    kind = "hls" if ".m3u8" in urlsplit(child).path.lower() else "mp4"
                    found.append((kind, child))
            elif isinstance(child, (dict, list)):
                found.extend(media_candidates(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(media_candidates(child))
    return found


class Catalog:
    def __init__(self, root):
        self.root = Path(root)
        state = self.root / ".state"
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        state.chmod(0o700)
        self.db = sqlite3.connect(str(state / "catalog.sqlite3"))
        (state / "catalog.sqlite3").chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS lessons (
            course TEXT NOT NULL, id TEXT NOT NULL, url TEXT NOT NULL,
            title TEXT NOT NULL, date TEXT, status TEXT NOT NULL DEFAULT 'pending',
            path TEXT, error TEXT, size_bytes INTEGER, PRIMARY KEY(course, id))""")
        self.db.commit()

        if 'size_bytes' not in {column[1] for column in self.db.execute('PRAGMA table_info(lessons)')}:
            self.db.execute('ALTER TABLE lessons ADD COLUMN size_bytes INTEGER')
            self.db.commit()

    def add(self, course, url, title="", date=None, size_bytes=None):
        rid = webex_id(url)
        if not rid:
            return False
        old = self.db.execute("SELECT 1 FROM lessons WHERE course=? AND id=?", (course, rid)).fetchone()
        self.db.execute("""INSERT INTO lessons(course,id,url,title,date) VALUES(?,?,?,?,?)
            ON CONFLICT(course,id) DO UPDATE SET url=excluded.url,
            title=CASE WHEN excluded.title=excluded.id THEN lessons.title ELSE excluded.title END,
            date=COALESCE(excluded.date,lessons.date)""", (course, rid, url, title.strip()[:240] or rid, date))
        if size_bytes is not None:
            self.db.execute('UPDATE lessons SET size_bytes=? WHERE course=? AND id=?', (size_bytes, course, rid))
        self.db.commit()
        return old is None

    def rows(self, course=None):
        if course:
            return self.db.execute("SELECT * FROM lessons WHERE course=? ORDER BY COALESCE(date,''),id", (course,)).fetchall()
        return self.db.execute("SELECT * FROM lessons ORDER BY course,COALESCE(date,''),id").fetchall()

    def update(self, row, status, path=None, error=None):
        self.db.execute("UPDATE lessons SET status=?,path=COALESCE(?,path),error=? WHERE course=? AND id=?",
                        (status, str(path) if path else None, error, row["course"], row["id"]))
        self.db.commit()

    def folder(self, row):
        if row["path"]:
            return self.root / row["path"]
        name = (row["date"] + "_" if row["date"] else "") + slug(row["title"]) + "_" + row["id"]
        return self.root / "corsi" / slug(row["course"]) / name


def validate_video(path):
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                 "format=duration:stream=codec_type", "-of", "json", str(path)],
                                capture_output=True, timeout=60, check=True)
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        kinds = {s.get("codec_type") for s in data.get("streams", [])}
        if duration <= 0 or "video" not in kinds or "audio" not in kinds:
            raise DownloadError("File senza durata valida, video o audio: non segnato come completo.")
        return {"duration_seconds": duration, "streams": sorted(kinds), "bytes": Path(path).stat().st_size}
    except (subprocess.SubprocessError, ValueError, OSError):
        raise DownloadError("Verifica ffprobe fallita; controlla file e installazione FFmpeg.") from None


def download_mp4(client, url, target, progress=None):
    """Ripresa solo con validatore HTTP; non concatena versioni diverse di un video."""
    target = Path(target)
    partial = target.with_suffix(".mp4.part")
    info = partial.with_suffix(".json")
    previous = {}
    if info.exists():
        try:
            previous = json.loads(info.read_text())
        except (OSError, ValueError):
            pass
    offset = partial.stat().st_size if partial.exists() else 0
    validator = previous.get("validator")
    if not validator:
        offset = 0
    headers = {"Accept-Encoding": "identity"}
    if offset:
        headers.update({"Range": "bytes=%d-" % offset, "If-Range": validator})
    with client.stream("GET", url, headers=headers) as response:
        if response.status_code == 416 and offset:
            info.unlink(missing_ok=True)
            return download_mp4(client, url, target, progress)
        if response.status_code not in (200, 206):
            raise DownloadError("Download HTTP %d; potrebbe servire un nuovo login." % response.status_code)
        ctype = response.headers.get("content-type", "").lower()
        if any(x in ctype for x in ("text/html", "application/json", "mpegurl")):
            raise DownloadError("Il server ha restituito una pagina o playlist invece del video.")
        total = None
        if response.status_code == 206:
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("content-range", ""))
            if not match or int(match[1]) != offset:
                raise DownloadError("Content-Range incoerente: ripresa interrotta.")
            total = int(match[3])
            if int(match[2]) != total - 1:
                raise DownloadError("Il server ha restituito un intervallo incompleto.")
        else:
            offset = 0
            if response.headers.get("content-length"):
                total = int(response.headers["content-length"])
        new_validator = response.headers.get("etag")
        if new_validator and new_validator.startswith("W/"):
            new_validator = None
        new_validator = new_validator or response.headers.get("last-modified")
        info.write_text(json.dumps({"validator": new_validator}))
        written = offset
        with partial.open("ab" if offset else "wb") as out:
            for chunk in response.iter_raw():
                out.write(chunk)
                written += len(chunk)
                if progress:
                    progress(written, total)
        if total is not None and written != total:
            raise DownloadError("Download incompleto: file parziale conservato per la ripresa.")
    details = validate_video(partial)
    partial.replace(target)
    info.unlink(missing_ok=True)
    return details
