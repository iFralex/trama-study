"""Offline UI and isolated native worker for slide/video alignment."""
import asyncio
import json
import math
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from .browser import ask
from .core import DownloadError, slug
from .local_jobs import atomic_json, job_lock
from .ui import course_name, lesson_name, show_date


async def child(args, env=None):
    process = await asyncio.create_subprocess_exec(*map(str, args), env=env)
    try:
        return await process.wait()
    except asyncio.CancelledError:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        raise


async def ensure_runtime(root):
    runtime = Path(root) / '.state/slides-runtime'
    python = runtime / 'bin/python'
    if python.is_file():
        probe = await asyncio.create_subprocess_exec(str(python), '-c',
            'import cv2, numpy, pymupdf, av', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if await probe.wait() == 0:
            if not shutil.which('tesseract'):
                raise DownloadError('Serve Tesseract OCR: installalo con brew install tesseract.')
            return python
    from .config import project_root
    candidates = ['/opt/homebrew/bin/python3.12', '/opt/homebrew/bin/python3', shutil.which('python3.12')]
    base = next((value for value in candidates if value and Path(value).is_file()), None)
    if base is None:
        raise DownloadError('Per l’analisi slide serve Python 3.12 nativo: brew install python@3.12. Il Python dell’app resta invariato.')
    if not shutil.which('tesseract'):
        raise DownloadError('Serve Tesseract OCR: installalo con brew install tesseract.')
    print('Preparo gli strumenti visivi nella cartella dati (solo al primo utilizzo)…', flush=True)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    with job_lock(runtime.parent / 'slides-setup.lock'):
        if not python.exists() and await child([base, '-m', 'venv', runtime]):
            raise DownloadError('Creazione dell’ambiente per le slide non riuscita.')
        scratch = runtime.parent / 'slides-tmp'
        scratch.mkdir(exist_ok=True)
        env = dict(os.environ, TMPDIR=str(scratch))
        code = await child([python, '-m', 'pip', 'install', '--no-cache-dir', '-r',
                            project_root() / 'requirements-slides.txt'], env)
        if code:
            raise DownloadError('Installazione degli strumenti visivi non completata. Puoi riprovare.')
    return python


async def align_course(catalog, query=None, all_pending=False, limit=None, lesson_id=None,
                       start=0.0, end=None, step=2.0, crop=None, pdf_filter=None, index_only=False):
    from .transcribe import select_local_course
    from .materials import selection_numbers
    course = await select_local_course(catalog, query, purpose='analizzare')
    rows = [r for r in catalog.rows(course) if (catalog.folder(r) / 'video.mp4').is_file()]
    materials = catalog.root / 'corsi' / slug(course) / 'materiali'
    if not materials.is_dir():
        raise DownloadError('Scarica prima i materiali del corso da WeBeep.')
    if lesson_id:
        rows = [r for r in rows if r['id'].startswith(lesson_id)]
        if len(rows) != 1:
            raise DownloadError('Identificativo lezione assente o ambiguo; usa status per vedere gli ID.')
    elif limit:
        rows = rows[:limit]
    elif not all_pending and not index_only:
        print('\n%s · %d lezioni scaricate.' % (course_name(course), len(rows)))
        print('Le analisi complete vengono verificate e saltate; quelle interrotte vengono riprese.')
        while True:
            print('1) Analizza tutte le lezioni\n2) Prova: analizza la prima\n3) Scegli le lezioni\nq) Indietro')
            value = (await ask('Scelta [1] > ')).strip().lower() or '1'
            if value == 'q':
                return 0
            if value in ('1', '2'):
                if value == '2':
                    rows = rows[:1]
                break
            if value == '3':
                for i, row in enumerate(rows, 1):
                    print('%d) %s · %s' % (i, show_date(row['date']), lesson_name(row['title'])))
                try:
                    selected = selection_numbers(await ask('Numeri o intervalli (es. 1,3-5) > '), len(rows))
                    rows = [rows[i] for i in selected]
                    break
                except ValueError as exc:
                    print(str(exc))
    if not math.isfinite(step) or not .2 <= step <= 10 or not math.isfinite(start) or start < 0 or (end is not None and (not math.isfinite(end) or end <= start)):
        raise DownloadError('Intervallo non valido o campionamento fuori da 0.2–10 secondi.')
    if crop and (len(crop) != 4 or min(crop[:2]) < 0 or min(crop[2:]) <= 0):
        raise DownloadError('Ritaglio non valido: usa x y larghezza altezza in pixel.')
    python = await ensure_runtime(catalog.root)
    request_dir = catalog.root / '.state/slides-jobs'
    request_dir.mkdir(parents=True, exist_ok=True)
    request = request_dir / (uuid.uuid4().hex + '.json')
    items = [] if index_only else [dict(video=str(catalog.folder(r) / 'video.mp4'),
              output=str(catalog.folder(r) / ('allineamento' if start == 0 and end is None else
                     'allineamento/prove/%.3f-%.3f' % (start, end if end is not None else -1)))) for r in rows]
    atomic_json(request, {'materials': str(materials), 'index': str(materials.parent / 'indice-materiali'),
                         'items': items, 'options': dict(start=start, end=end, step=step, crop=crop, pdf_filter=pdf_filter)})
    from .config import project_root
    env = dict(os.environ, PYTHONPATH=str(project_root()), PYTHONUNBUFFERED='1', TMPDIR=str(catalog.root / '.state/slides-tmp'))
    Path(env['TMPDIR']).mkdir(exist_ok=True)
    print('Analisi locale: indice materiali → cambi schermata → riconoscimento → confini temporali.', flush=True)
    code = await child([python, '-m', 'polimi_lectures.slide_worker', '--request', request], env)
    if code:
        raise DownloadError('Analisi non completata. Riprova la stessa operazione: i passaggi già salvati saranno riutilizzati.')
    print('Risultati in ogni cartella lezione: allineamento/allineamento.md, .csv e .json.')
    return 0
