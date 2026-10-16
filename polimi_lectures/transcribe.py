"""Local, chunked Whisper transcription with durable resumable checkpoints."""
import asyncio
import hashlib
import json
import math
import re
import shutil
import uuid
import wave
from pathlib import Path

from .browser import ask
from .core import DownloadError
from .local_jobs import atomic_bytes, atomic_json, file_hash, job_lock
from .ui import course_name, lesson_name, show_date
from .whisper_models import choose_model, engine_path, load_settings, save_settings, validate_model

VERSION = 1
CHUNK_SECONDS = 300
OUTPUTS = ('trascrizione.txt', 'trascrizione.srt', 'trascrizione.json')


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def source_stat(video):
    info = Path(video).stat()
    return {'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns}


def transcript_complete(video, directory):
    directory = Path(directory)
    marker = read_json(directory / 'completa.json')
    if not isinstance(marker, dict) or marker.get('version') != VERSION or marker.get('source_stat') != source_stat(video):
        return False
    hashes = marker.get('outputs')
    if not isinstance(hashes, dict) or set(hashes) != set(OUTPUTS):
        return False
    return all((directory / name).is_file() and file_hash(directory / name) == hashes[name] for name in OUTPUTS)


def timestamp(seconds):
    ms = max(0, int(round(seconds * 1000)))
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return '%02d:%02d:%02d,%03d' % (hours, minutes, seconds, ms)


def normalized_segments(data, start, length):
    if not isinstance(data, dict) or not isinstance(data.get('transcription'), list):
        raise DownloadError('Whisper non ha prodotto una trascrizione JSON valida.')
    result = []
    previous = 0
    for segment in data['transcription']:
        try:
            offsets = segment['offsets']
            begin, end = float(offsets['from']) / 1000, float(offsets['to']) / 1000
            text = segment['text'].strip()
            if not all(math.isfinite(v) for v in (begin, end)) or begin < 0 or end < begin or begin < previous or end > length + 5:
                raise ValueError()
        except (KeyError, TypeError, ValueError, AttributeError):
            raise DownloadError('Timestamp Whisper non validi: il blocco non è segnato come completato.')
        previous = begin
        if text and begin < length:
            result.append({'start': round(start + begin, 3), 'end': round(start + min(end, length), 3), 'text': text})
    return result


def saved_chunk(path, index, start, end):
    chunk = read_json(path)
    if not isinstance(chunk, dict) or chunk.get('index') != index or chunk.get('start') != start or chunk.get('end') != end:
        return None
    segments = chunk.get('segments')
    if not isinstance(segments, list) or chunk.get('sha256') != digest_json(segments):
        return None
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get('text'), str):
            return None
        begin, finish = segment.get('start'), segment.get('end')
        if not isinstance(begin, (int, float)) or not isinstance(finish, (int, float)) or not start <= begin <= finish <= end:
            return None
    return chunk


async def run_tool(args, log, label):
    with Path(log).open('wb') as stream:
        process = await asyncio.create_subprocess_exec(*map(str, args), stdout=stream, stderr=stream)
        try:
            while True:
                try:
                    code = await asyncio.wait_for(process.wait(), timeout=30)
                    break
                except asyncio.TimeoutError:
                    print('  %s: elaborazione in corso…' % label, flush=True)
        except asyncio.CancelledError:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            raise
    if code != 0:
        raise DownloadError('%s non completato. I blocchi già salvati restano disponibili. Dettagli: %s' % (label, log))


async def probe_audio(video):
    process = await asyncio.create_subprocess_exec(
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,duration',
        '-of', 'json', str(video), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=60)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    try:
        data = json.loads(output)
        audio = next(s for s in data.get('streams', []) if s.get('codec_type') == 'audio')
        value = audio.get('duration')
        duration = float(value if value and value != 'N/A' else data['format']['duration'])
        if process.returncode or not math.isfinite(duration) or duration <= 0:
            raise ValueError()
        return duration
    except (ValueError, KeyError, StopIteration):
        raise DownloadError('Il video non contiene audio con durata valida: %s' % video)


async def transcribe_video(video, directory, model, language, engine, model_sha=None, engine_version=None, chunk_seconds=CHUNK_SECONDS):
    video, directory, model = Path(video).resolve(), Path(directory), Path(model).resolve()
    if chunk_seconds < 1:
        raise DownloadError('La durata dei blocchi deve essere positiva.')
    directory.mkdir(parents=True, exist_ok=True)
    with job_lock(directory / '.lock'):
        if transcript_complete(video, directory):
            return 'present'
        before = source_stat(video)
        video_sha = await asyncio.to_thread(file_hash, video)
        if source_stat(video) != before:
            raise DownloadError('Il video è cambiato durante la lettura. Riprova quando il download è terminato.')
        model_sha = model_sha or await asyncio.to_thread(file_hash, model)
        duration = max(0.001, round(await probe_audio(video), 3))
        identity = {'version': VERSION, 'video_sha256': video_sha, 'model_sha256': model_sha,
                    'language': language, 'chunk_seconds': chunk_seconds, 'engine_version': engine_version or 'whisper.cpp'}
        run_id = digest_json(identity)[:24]
        run = directory / 'sessioni' / run_id
        chunks = run / 'blocchi'
        chunks.mkdir(parents=True, exist_ok=True)
        total = int(math.ceil(duration / chunk_seconds))
        intervals = [(i, i * chunk_seconds, round(min(duration, (i + 1) * chunk_seconds), 3)) for i in range(total)]
        existing = {i: saved_chunk(chunks / ('%05d.json' % i), i, start, end) for i, start, end in intervals}
        completed = sum(value is not None for value in existing.values())
        print('  %s: %d/%d blocchi già salvati.' % ('Riprendo' if completed else 'Trascrizione', completed, total))
        status = {'identity': identity, 'source': str(video), 'model': str(model), 'duration': duration, 'total_chunks': total}
        atomic_json(run / 'stato.json', dict(status, completed_chunks=completed))
        work = run / ('lavoro-' + uuid.uuid4().hex)
        work.mkdir(exist_ok=True)
        audio, output = work / 'audio.wav', work / 'whisper'
        all_segments = []
        for i, start, end in intervals:
            previous = existing[i]
            if previous is not None:
                all_segments.extend(previous['segments'])
                continue
            print('  Blocco %d/%d · %s → %s' % (i + 1, total, timestamp(start)[:8], timestamp(end)[:8]), flush=True)
            for name in ('audio.wav', 'whisper.json'):
                (work / name).unlink(missing_ok=True)
            await run_tool(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-ss', str(start), '-i', video, '-t', str(end - start),
                            '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', audio], work / 'ffmpeg.log', 'Estrazione audio')
            with wave.open(str(audio), 'rb') as wav:
                actual = wav.getnframes() / wav.getframerate()
            if actual <= 0 or abs(actual - (end - start)) > 1:
                raise DownloadError('Audio estratto incompleto: il blocco non è segnato come completato.')
            args = [engine, '-m', model, '-f', audio, '-l', language, '-oj', '-of', output, '-np']
            if all_segments:
                args += ['--prompt', ' '.join(s['text'] for s in all_segments[-8:])[-600:]]
            await run_tool(args, work / 'whisper.log', 'Whisper')
            segments = normalized_segments(read_json(output.with_suffix('.json')), start, end - start)
            chunk = {'index': i, 'start': start, 'end': end, 'segments': segments, 'sha256': digest_json(segments)}
            atomic_json(chunks / ('%05d.json' % i), chunk)
            all_segments.extend(segments)
            completed += 1
            atomic_json(run / 'stato.json', dict(status, completed_chunks=completed))
            audio.unlink(missing_ok=True)
            output.with_suffix('.json').unlink(missing_ok=True)
            print('  Salvato · %d%% · %d/%d blocchi' % (int(completed * 100 / total), completed, total), flush=True)
        if source_stat(video) != before:
            raise DownloadError('Il video è cambiato: trascrizione conservata nei blocchi, ma non segnata come completa.')
        text = '\n'.join(segment['text'] for segment in all_segments) + '\n'
        subtitles = '\n\n'.join('%d\n%s --> %s\n%s' % (i, timestamp(segment['start']), timestamp(segment['end']), segment['text'])
                                for i, segment in enumerate(all_segments, 1)) + '\n'
        atomic_bytes(directory / OUTPUTS[0], text.encode('utf-8'))
        atomic_bytes(directory / OUTPUTS[1], subtitles.encode('utf-8'))
        atomic_json(directory / OUTPUTS[2], dict(status, segments=all_segments))
        atomic_json(directory / 'completa.json', {'version': VERSION, 'source_stat': before, 'identity': identity,
                    'outputs': {name: file_hash(directory / name) for name in OUTPUTS}})
        return 'transcribed'


async def select_local_course(catalog, query, purpose="trascrivere"):
    from .config import load_config, remember_course, saved_course
    from .guided import choose_course
    available = sorted({row['course'] for row in catalog.rows() if (catalog.folder(row) / 'video.mp4').is_file()})
    if not available:
        raise DownloadError('Non ci sono lezioni scaricate da %s. Scarica prima almeno una lezione.' % purpose)
    preferences = load_config()
    query = query or preferences.get('last_course', '')
    if not query:
        query = (await ask('Nome del corso da %s > ' % purpose)).strip()
    selected = await choose_course([{'label': label, 'url': ''} for label in available], query)
    old = saved_course(preferences, selected['label'])
    try:
        remember_course(selected['label'], old.get('url'), query)
    except OSError:
        print('Preferenza del corso non salvata; l’operazione può proseguire sul disco dati.')
    return selected['label']


async def transcribe_course(catalog, query=None, model=None, model_name=None, language=None, engine=None,
                            chunk_seconds=CHUNK_SECONDS, all_pending=False, limit=None):
    course = await select_local_course(catalog, query)
    rows = [row for row in catalog.rows(course) if (catalog.folder(row) / 'video.mp4').is_file()]
    pending, present = [], 0
    for row in rows:
        folder = catalog.folder(row)
        if transcript_complete(folder / 'video.mp4', folder / 'trascrizione'):
            present += 1
        else:
            pending.append(row)
    print('\n%s · %d lezioni scaricate, %d già trascritte, %d da trascrivere/riprendere.' %
          (course_name(course), len(rows), present, len(pending)))
    if not pending:
        print('Tutte le trascrizioni sono complete.')
        return 0
    if limit:
        pending = pending[:limit]
    elif not all_pending:
        from .materials import selection_numbers
        while True:
            print('1) Trascrivi tutte quelle da completare\n2) Prova: trascrivi la prima\n3) Scegli le lezioni\nq) Indietro')
            value = (await ask('Scelta [1] > ')).strip().lower() or '1'
            if value == 'q':
                return 0
            if value == '1':
                break
            if value == '2':
                pending = pending[:1]
                break
            if value == '3':
                for i, row in enumerate(pending, 1):
                    print('%d) %s · %s' % (i, show_date(row['date']), lesson_name(row['title'])))
                try:
                    numbers = selection_numbers(await ask('Numeri o intervalli (es. 1,3-5) > '), len(pending))
                    pending = [pending[i] for i in numbers]
                    break
                except ValueError as exc:
                    print(str(exc))
    engine = engine_path(engine)
    for tool in ('ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            raise DownloadError('Serve %s per estrarre l’audio delle lezioni.' % tool)
    selected_model = await choose_model(catalog.root, model, model_name)
    if selected_model is None:
        return 0
    settings = load_settings(catalog.root)
    if not language:
        default = settings.get('language', 'auto')
        while True:
            language = (await ask('Lingua [1 auto, 2 inglese, 3 italiano; Invio = %s] > ' % default)).strip().lower() or default
            language = {'1': 'auto', '2': 'en', '3': 'it'}.get(language, language)
            if language == 'auto' or re.fullmatch(r'[a-z]{2,3}', language):
                break
            print('Usa auto, en, it oppure un codice lingua Whisper.')
    if language != 'auto' and not re.fullmatch(r'[a-z]{2,3}', language):
        raise DownloadError('Lingua non valida: usa auto, en, it oppure un codice lingua Whisper.')
    if '.en' in selected_model.name and language not in ('auto', 'en'):
        raise DownloadError('Il modello .en è solo inglese: scegli un modello multilingue per questa lingua.')
    save_settings(catalog.root, language=language)
    print('Verifico il modello…', flush=True)
    model_before = source_stat(selected_model)
    model_sha = await asyncio.to_thread(file_hash, selected_model)
    if source_stat(selected_model) != model_before:
        raise DownloadError('Il file modello è cambiato durante la lettura. Riprova.')
    # Include the engine version in checkpoints to avoid mixing different decoders.
    process = await asyncio.create_subprocess_exec(engine, '--version', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        version, _ = await asyncio.wait_for(process.communicate(), timeout=15)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    engine_version = version.decode('utf-8', 'replace').strip()
    if process.returncode or not engine_version:
        raise DownloadError('Il motore Whisper non risponde correttamente.')
    failed = completed = 0
    for i, row in enumerate(pending, 1):
        print('\n[%d/%d] %s · %s' % (i, len(pending), show_date(row['date']), lesson_name(row['title'])), flush=True)
        try:
            if source_stat(selected_model) != model_before:
                raise DownloadError('Il file modello è cambiato durante la trascrizione. Riavvia l’operazione.')
            folder = catalog.folder(row)
            await transcribe_video(folder / 'video.mp4', folder / 'trascrizione', selected_model, language, engine,
                                   model_sha=model_sha, engine_version=engine_version, chunk_seconds=chunk_seconds)
            completed += 1
            print('  Trascrizione completa: %s' % (folder / 'trascrizione'))
        except (DownloadError, OSError, wave.Error) as exc:
            failed += 1
            print('  Non completata: %s' % exc)
    print('\nTrascrizioni: %d completate, %d già presenti, %d non riuscite.' % (completed, present, failed))
    return int(bool(failed))
