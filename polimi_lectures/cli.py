import argparse
import asyncio
import http.cookiejar
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from .core import Catalog, DownloadError, download_mp4, playlist_mp4, public_recording_url, validate_video, webex_id
from .ui import lesson_name, show_date


def root_path(args):
    from .config import data_root
    return data_root(args.root)


def make_client(cookies, agent, referer):
    import httpx
    jar = http.cookiejar.CookieJar()
    for c in cookies:
        domain = c["domain"]
        jar.set_cookie(http.cookiejar.Cookie(
            version=0, name=c["name"], value=c["value"], port=None, port_specified=False,
            domain=domain, domain_specified=domain.startswith("."), domain_initial_dot=domain.startswith("."),
            path=c.get("path", "/"), path_specified=True, secure=c.get("secure", True),
            expires=int(c["expires"]) if c.get("expires", -1) > 0 else None,
            discard=False, comment=None, comment_url=None, rest={}))
    # Referer minimo: evita di inoltrare query di autenticazione ai CDN.
    parsed = urlsplit(referer)
    safe_referer = "%s://%s/" % (parsed.scheme, parsed.netloc)
    return httpx.Client(cookies=jar, headers={"User-Agent": agent, "Referer": safe_referer},
                        follow_redirects=True, timeout=httpx.Timeout(60, connect=20))


def progress_reporter(batch=None):
    last = [0]
    started = time.monotonic()
    baseline = [None]
    rendered = [0]
    def report(size, total):
        if batch:
            batch.report(size, total)
        now = time.monotonic()
        if baseline[0] is None:
            baseline[0] = size
        complete = bool(total and size >= total)
        if not complete and (size < 1_000_000 or now - last[0] < (1 if sys.stdout.isatty() else 5)):
            return
        text = ('%3d%% · %.1f / %.1f MB' % (min(100, size * 100 / total), size / 1_000_000, total / 1_000_000)
                if total else '%.1f MB scaricati' % (size / 1_000_000))
        speed = (size - baseline[0]) / max(now - started, 0.1)
        if total and speed > 0 and not complete:
            seconds = max(0, int((total - size) / speed))
            text += ' · circa %d:%02d rimanenti' % (seconds // 60, seconds % 60)
        if batch:
            text += '\n  ' + batch.text()
        output = '  ' + text
        if sys.stdout.isatty():
            if rendered[0]:
                print(('\x1b[1A\r\x1b[2K') * rendered[0], end='')
            width = max(1, shutil.get_terminal_size((80, 24)).columns)
            rendered[0] = sum(max(1, (len(line) + width - 1) // width) for line in output.split('\n'))
        print(output, flush=True)
        if complete:
            rendered[0] = 0
        last[0] = now
    return report


async def download_hls(url, target, cookies, agent, referer, progress=None):
    # Cookie con domain/path: non inoltra una Cookie header globale a ogni host HLS.
    lines = []
    for c in cookies:
        if (c["domain"].lstrip(".").endswith(".webex.com") or c["domain"].lstrip(".") == "webex.com"):
            line = "%s=%s; path=%s; domain=%s;" % (c["name"], c["value"], c.get("path", "/"), c["domain"])
            if c.get("secure"):
                line += " secure;"
            lines.append(line)
    partial = target.with_suffix(".hls.part.mp4")
    parsed = urlsplit(referer)
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-user_agent", agent, "-referer", "%s://%s/" % (parsed.scheme, parsed.netloc)]
    if lines:
        args += ["-cookies", "\n".join(lines) + "\n"]
    args += ["-i", url, "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-movflags", "+faststart", str(partial)]
    print("  Scarico il video…", flush=True)
    process = await asyncio.create_subprocess_exec(*args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        while True:
            try:
                code = await asyncio.wait_for(process.wait(), timeout=1)
                break
            except asyncio.TimeoutError:
                if progress and partial.exists():
                    progress(partial.stat().st_size, None)
    except asyncio.CancelledError:
        if process.returncode is None:
            process.terminate()
            await process.wait()
        raise
    if code:
        raise DownloadError("FFmpeg non ha completato HLS; riprova dopo un nuovo accesso.")
    details = validate_video(partial)
    partial.replace(target)
    return details


async def download_one(context, catalog, row, batch=None):
    from .browser import resolve
    import httpx
    folder = catalog.folder(row)
    folder.mkdir(parents=True, exist_ok=True)
    relative = folder.relative_to(catalog.root)
    target = folder / "video.mp4"
    if target.exists():
        try:
            details = validate_video(target)
            write_metadata(folder, row, details)
            catalog.update(row, "complete", relative)
            print("  Già scaricato · file verificato.")
            return 'present'
        except DownloadError:
            print("  File presente ma non valido: nuovo download.")
    catalog.update(row, "downloading", relative)
    candidates, cookies, agent, referer, title = await resolve(context, row)
    if title:
        catalog.add(row["course"], row["url"], title, row["date"])
        row = next(r for r in catalog.rows(row["course"]) if r["id"] == row["id"])
    failures = []
    with make_client(cookies, agent, referer) as client:
        # Prima MP4 diretto; poi playlist/HLS. Gli URL firmati restano in memoria.
        for kind, url in sorted(candidates, key=lambda item: item[0] != "mp4"):
            try:
                if kind == "mp4":
                    details = download_mp4(client, url, target, progress_reporter(batch))
                else:
                    response = client.get(url)
                    if response.status_code != 200:
                        raise DownloadError("Playlist HTTP %d." % response.status_code)
                    direct = playlist_mp4(response.text, str(response.url))
                    if direct:
                        try:
                            details = download_mp4(client, direct, target, progress_reporter(batch))
                        except (DownloadError, httpx.HTTPError):
                            details = await download_hls(url, target, cookies, agent, referer, progress_reporter(batch))
                    else:
                        details = await download_hls(url, target, cookies, agent, referer, progress_reporter(batch))
                write_metadata(folder, row, details)
                catalog.update(row, "complete", relative)
                print("  Verificato · %.1f minuti." % (details["duration_seconds"] / 60))
                return 'downloaded'
            except (DownloadError, httpx.HTTPError) as exc:
                reason = str(exc) if isinstance(exc, DownloadError) else "Errore di rete (%s)." % type(exc).__name__
                failures.append(reason)
    raise DownloadError(failures[-1] if failures else "Nessuna sorgente scaricabile.")


def write_metadata(folder, row, details):
    data = {"id": row["id"], "course": row["course"], "title": row["title"], "date": row["date"],
            "source": public_recording_url(row["url"]), "media": details}
    temp = folder / "metadata.json.tmp"
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(folder / "metadata.json")


async def browser_command(args, catalog):
    from playwright.async_api import async_playwright
    from .browser import ARCHIVE, ask, discover, launch
    async with async_playwright() as playwright:
        context = await launch(playwright, catalog.root, args.channel)
        try:
            if args.command == "login":
                page = context.pages[0] if context.pages else await context.new_page()
                try:
                    await page.goto(ARCHIVE, wait_until="domcontentloaded", timeout=45000)
                except Exception:
                    pass
                print("Accedi a Polimi e apri almeno una registrazione Webex per autenticarti anche lì.")
                await ask("Quando hai finito, premi Invio qui per salvare la sessione > ")
            elif args.command == "discover":
                await discover(context, catalog, args.course, args.url, args.lesson_selector)
            elif args.command in ('wizard', 'materials'):
                from .workflow import course_workflow
                return await course_workflow(context, catalog, args.course, materials_first=args.command == 'materials')
            elif args.command == "download":
                known = sorted({row['course'] for row in catalog.rows()})
                if args.course not in known:
                    from .guided import choose_course, course_matches
                    if any(course_matches(args.course, name) for name in known):
                        selected = await choose_course([{'label': name, 'url': ''} for name in known], args.course)
                        args.course = selected['label']
                rows = [r for r in catalog.rows(args.course) if not args.before or (r['date'] and r['date'] <= args.before)]
                if args.before:
                    unknown = sum(r["date"] is None for r in catalog.rows(args.course))
                    if unknown:
                        print("Filtro data: %d lezioni senza data escluse. Usa add --date per assegnarla." % unknown)
                if args.limit:
                    rows = [r for r in rows if r["status"] != "complete" or not (catalog.folder(r) / "video.mp4").exists()][:args.limit]
                if not rows:
                    print('Nessuna lezione da scaricare. Esegui prima discover o add.')
                from .workflow import download_rows
                return int(bool(await download_rows(context, catalog, rows)))
        finally:
            assistant = getattr(context, "_polimi_assistant", None)
            if assistant:
                await assistant.stop()
            await context.close()
    return 0


def iso_date(value):
    from datetime import date
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError("Usa una data valida YYYY-MM-DD.")


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Deve essere maggiore di zero.")
    return number


def parser():
    p = argparse.ArgumentParser(description="Catalogo e download incrementale Polimi/Webex.")
    p.add_argument("--root", help="Cartella dati; altrimenti usa quella scelta nel setup")
    p.add_argument("--channel", choices=["chrome", "msedge"], help="Usa un browser installato invece di Chromium")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("login", help="Accesso manuale con sessione persistente")
    wizard = commands.add_parser("wizard", help="Login, ricerca corso, registrazioni e scelta date/prova")
    wizard.add_argument("--course")
    materials = commands.add_parser('materials', help='Scarica tutti o alcuni materiali WeBeep')
    materials.add_argument('--course')
    d = commands.add_parser("discover", help="Raccogli registrazioni dal browser")
    d.add_argument("--course", required=True)
    d.add_argument("--url", help="Pagina RecMan o WeBeep attuale, facoltativa")
    d.add_argument("--lesson-selector", help="Selettore CSS dei soli pulsanti di riproduzione, se necessario")
    a = commands.add_parser("add", help="Importa collegamento Webex o file con un URL per riga")
    a.add_argument("--course", required=True)
    a.add_argument("--url")
    a.add_argument("--file", type=Path)
    a.add_argument("--title", default="")
    a.add_argument("--date", type=iso_date)
    dl = commands.add_parser("download", help="Scarica e verifica il catalogo")
    dl.add_argument("--course", required=True)
    dl.add_argument("--before", type=iso_date, help="Data massima inclusa; esclude date sconosciute")
    dl.add_argument("--limit", type=positive, help="Numero massimo di lezioni non completate")
    s = commands.add_parser("status", help="Mostra catalogo senza cookie o URL firmati")
    s.add_argument("--course")
    tr = commands.add_parser('transcribe', help='Trascrivi localmente le lezioni scaricate, riprendendo i blocchi salvati')
    tr.add_argument('--course')
    models = tr.add_mutually_exclusive_group()
    models.add_argument('--model', type=Path, help='File modello Whisper GGML .bin già presente')
    models.add_argument('--model-name', help='Nome del modello da scaricare dal catalogo ufficiale')
    tr.add_argument('--language', help='auto, en, it oppure codice lingua Whisper')
    tr.add_argument('--engine', help='Percorso di whisper-cli (facoltativo)')
    tr.add_argument('--chunk-seconds', type=positive, default=300, help='Durata dei blocchi per la ripresa, in secondi')
    tr.add_argument('--all', dest='all_pending', action='store_true', help='Trascrivi tutte le lezioni non complete')
    tr.add_argument('--limit', type=positive, help='Numero massimo di lezioni da trascrivere')
    wm = commands.add_parser('whisper-model', help='Scegli o scarica il modello Whisper')
    choices = wm.add_mutually_exclusive_group()
    choices.add_argument('--model', type=Path)
    choices.add_argument('--model-name')
    al = commands.add_parser('align', help='Associa pagine PDF e notebook agli intervalli del video, con ripresa')
    al.add_argument('--course')
    al.add_argument('--all', dest='all_pending', action='store_true')
    al.add_argument('--limit', type=positive)
    al.add_argument('--lesson-id', help='ID o prefisso univoco dal catalogo status')
    al.add_argument('--start', type=float, default=0.0, help='Inizio della prova in secondi')
    al.add_argument('--end', type=float, help='Fine della prova in secondi')
    al.add_argument('--step', type=float, default=2.0, help='Passo scansione; scene più brevi possono sfuggire')
    al.add_argument('--crop', type=int, nargs=4, metavar=('X', 'Y', 'W', 'H'))
    al.add_argument('--pdf', dest='pdf_filter', action='append', help='Limita i PDF candidati a un nome file; ripetibile')
    al.add_argument('--index-only', action='store_true')
    commands.add_parser("doctor", help="Controlla dipendenze e browser")
    return p


def main(argv=None):
    os.umask(0o077)
    p = parser()
    args = p.parse_args(argv)
    try:
        selected_root = root_path(args)
    except (OSError, ValueError) as exc:
        print("Errore configurazione: %s" % exc, file=sys.stderr)
        return 1
    from .config import project_root
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(project_root() / ".state" / "browsers"))
    if args.command == 'whisper-model':
        from .whisper_models import choose_model
        try:
            model = asyncio.run(choose_model(selected_root, args.model, args.model_name))
            if model:
                print('Modello selezionato: %s' % model)
            return 0
        except KeyboardInterrupt:
            print('\nInterrotto. Il modello parziale è conservato per la ripresa.')
            return 130
        except (DownloadError, OSError, ValueError) as exc:
            print('Modello non disponibile: %s' % exc)
            return 1
        except Exception as exc:
            print('Download modello non completato (%s). Il file parziale è conservato: riprova per riprendere.' % type(exc).__name__)
            return 1
    if args.command == "doctor":
        failed = False
        print("Python: %s" % sys.version.split()[0])
        for tool in ("ffmpeg", "ffprobe"):
            location = shutil.which(tool)
            print("%s: %s" % (tool, location or "MANCANTE (installa FFmpeg)"))
            failed |= location is None
        try:
            import httpx
            from playwright.sync_api import sync_playwright
            print("HTTPX: %s" % httpx.__version__)
            with sync_playwright() as pw:
                available = Path(pw.chromium.executable_path).exists()
                print("Chromium: %s" % ("OK" if available else "MANCANTE: python -m playwright install chromium"))
                failed |= not available
        except ImportError:
            print("Dipendenze Python mancanti: esegui Setup.command")
            failed = True
        from .whisper_models import engine_path
        try:
            print('Whisper locale: %s' % engine_path())
        except DownloadError:
            print('Whisper locale: facoltativo, installabile con brew install whisper.cpp')
        return int(failed)
    try:
        catalog = Catalog(selected_root)
    except OSError as exc:
        print("Cartella dati non accessibile: %s" % exc, file=sys.stderr)
        return 1
    try:
        if args.command == 'transcribe':
            from .transcribe import transcribe_course
            return asyncio.run(transcribe_course(catalog, args.course, model=args.model, model_name=args.model_name,
                language=args.language, engine=args.engine, chunk_seconds=args.chunk_seconds,
                all_pending=args.all_pending, limit=args.limit))
        elif args.command == 'align':
            from .alignment import align_course
            return asyncio.run(align_course(catalog, args.course, all_pending=args.all_pending, limit=args.limit,
                lesson_id=args.lesson_id, start=args.start, end=args.end, step=args.step, crop=args.crop,
                pdf_filter=args.pdf_filter, index_only=args.index_only))
        elif args.command == "add":
            if bool(args.url) == bool(args.file):
                p.error("Specifica esattamente uno tra --url e --file.")
            urls = [args.url] if args.url else args.file.read_text(encoding="utf-8").splitlines()
            added = 0
            for url in urls:
                url = url.strip()
                if not url or url.startswith("#"):
                    continue
                if not webex_id(url):
                    raise DownloadError("Un collegamento non è un URL di registrazione Webex valido.")
                added += catalog.add(args.course, url, args.title, args.date)
            print("Nuove registrazioni: %d. Totale corso: %d." % (added, len(catalog.rows(args.course))))
        elif args.command == "status":
            rows = catalog.rows(args.course)
            for row in rows:
                print("%s | %s | %s | %s | %s" % (row["course"], row["date"] or "data sconosciuta", row["status"], row["id"][:8], row["title"]))
            print("Totale: %d; complete: %d; errori: %d" % (len(rows), sum(r["status"] == "complete" for r in rows), sum(r["status"] == "error" for r in rows)))
        else:
            if args.command in ("download", "wizard") and (not shutil.which("ffmpeg") or not shutil.which("ffprobe")):
                raise DownloadError("Servono ffmpeg e ffprobe. Installa FFmpeg e riprova.")
            return asyncio.run(browser_command(args, catalog))
        return 0
    except KeyboardInterrupt:
        print("\nInterrotto. Download parziali, trascrizioni e checkpoint di allineamento già salvati sono conservati.")
        return 130
    except (DownloadError, OSError) as exc:
        print("Errore: %s" % exc, file=sys.stderr)
        return 1
    except Exception as exc:
        # Le eccezioni Playwright/HTTP possono contenere URL con token: niente traceback.
        print("Errore %s. Controlla browser, sessione e doctor; nessun URL riservato mostrato." % type(exc).__name__, file=sys.stderr)
        return 1
    finally:
        catalog.db.close()


if __name__ == "__main__":
    sys.exit(main())
