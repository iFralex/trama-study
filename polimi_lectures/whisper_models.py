"""Model selection and verified, resumable GGML downloads."""
import asyncio
import json
import os
import platform
import re
import shutil
from pathlib import Path

import httpx

from .browser import ask
from .configure import parse_folder
from .core import DownloadError
from .local_jobs import atomic_json, file_hash, job_lock

REPOSITORY = 'https://huggingface.co/ggerganov/whisper.cpp'
API = 'https://huggingface.co/api/models/ggerganov/whisper.cpp'
MODEL_NAME = re.compile(r'ggml-((?:tiny|base|small|medium)(?:\.en)?(?:-q[58]_[01])?|large-v[123](?:-turbo)?(?:-q[58]_[01])?)\.bin')
PREFERRED = ['small', 'large-v3-turbo', 'small-q5_1', 'large-v3-turbo-q5_0', 'base', 'tiny', 'medium', 'large-v3']


def engine_path(override=None):
    candidates = [override] if override else (
        ['/opt/homebrew/bin/whisper-cli'] if platform.system() == 'Darwin' else [])
    if not override:
        candidates += [shutil.which('whisper-cli'), '/usr/local/bin/whisper-cli']
    for value in candidates:
        if value and Path(value).is_file() and os.access(value, os.X_OK):
            return str(Path(value).absolute())
    raise DownloadError('Motore Whisper assente. Installa whisper.cpp con «brew install whisper.cpp» e riprova.')


def validate_model(path):
    path = Path(path)
    if not path.is_file():
        raise DownloadError('Il modello non è un file disponibile: %s' % path)
    with path.open('rb') as stream:
        if stream.read(4) != b'lmgg':
            raise DownloadError('Serve un modello Whisper GGML .bin. I file .pt e i modelli CTranslate2 non sono compatibili con questo motore.')
    return path.resolve()


def settings_path(root):
    return Path(root) / '.state' / 'whisper' / 'settings.json'


def load_settings(root):
    path = settings_path(root)
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise DownloadError('Configurazione Whisper non valida.')
    return value


def save_settings(root, **changes):
    value = load_settings(root)
    value.update(changes)
    atomic_json(settings_path(root), value)


def parse_catalog(data):
    revision = data.get('sha', '')
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise DownloadError('Il catalogo modelli non contiene una revisione verificabile.')
    models = []
    for item in data.get('siblings', []):
        match = MODEL_NAME.fullmatch(item.get('rfilename', ''))
        lfs = item.get('lfs', {})
        checksum = lfs.get('sha256', '')
        size = lfs.get('size', item.get('size', 0))
        if match and re.fullmatch(r'[a-f0-9]{64}', checksum) and isinstance(size, int) and size > 0:
            models.append({'name': match[1], 'filename': item['rfilename'], 'sha256': checksum, 'bytes': size,
                           'url': REPOSITORY + '/resolve/' + revision + '/' + item['rfilename']})
    if not models:
        raise DownloadError('Nessun modello verificabile nel catalogo.')
    return sorted(models, key=lambda m: (PREFERRED.index(m['name']) if m['name'] in PREFERRED else len(PREFERRED), m['name']))


async def model_catalog(root):
    cache = Path(root) / '.state' / 'whisper' / 'model-catalog.json'
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            response = await client.get(API, params={'blobs': 'true'})
            response.raise_for_status()
            data = response.json()
        models = parse_catalog(data)
        atomic_json(cache, data)
        return models
    except (httpx.HTTPError, ValueError, DownloadError):
        if cache.exists():
            print('Catalogo online non disponibile: uso quello salvato.')
            return parse_catalog(json.loads(cache.read_text(encoding='utf-8')))
        raise DownloadError('Non riesco a leggere il catalogo modelli. Riprova con Internet disponibile oppure indica un modello già scaricato.')


async def download_model(root, model, client=None):
    directory = Path(root) / 'modelli' / 'whisper'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / model['filename']
    partial = directory / (model['filename'] + '.' + model['sha256'][:16] + '.part')
    with job_lock(directory / (model['filename'] + '.lock')):
        if target.exists() and await asyncio.to_thread(file_hash, target) == model['sha256']:
            print('Modello già presente e verificato.')
            return validate_model(target)
        offset = partial.stat().st_size if partial.exists() else 0
        if offset >= model['bytes']:
            if offset == model['bytes'] and await asyncio.to_thread(file_hash, partial) == model['sha256']:
                partial.replace(target)
                return validate_model(target)
            partial.replace(partial.with_suffix('.invalid'))
            offset = 0
        if shutil.disk_usage(directory).free < model['bytes'] - offset + 10_000_000:
            raise DownloadError('Spazio insufficiente nella cartella modelli: %s' % directory)
        from .cli import progress_reporter
        progress = progress_reporter()
        async def transfer(http):
            nonlocal offset
            headers = {'Accept-Encoding': 'identity'}
            if offset:
                headers['Range'] = 'bytes=%d-' % offset
            async with http.stream('GET', model['url'], headers=headers) as response:
                if response.status_code not in (200, 206):
                    raise DownloadError('Download modello HTTP %d. Il file parziale è conservato.' % response.status_code)
                if response.status_code == 206:
                    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('content-range', ''))
                    if not match or int(match[1]) != offset or int(match[3]) != model['bytes'] or int(match[2]) != model['bytes'] - 1:
                        raise DownloadError('Intervallo del modello incoerente: ripresa interrotta.')
                else:
                    offset = 0
                with partial.open('ab' if offset else 'wb') as stream:
                    async for chunk in response.aiter_bytes(256 * 1024):
                        stream.write(chunk)
                        offset += len(chunk)
                        progress(offset, model['bytes'])
                    stream.flush()
                    os.fsync(stream.fileno())
        print('Scarico %s nella cartella %s' % (model['name'], directory))
        if client is None:
            async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(60, connect=20)) as http:
                await transfer(http)
        else:
            await transfer(client)
        if offset != model['bytes']:
            raise DownloadError('Modello incompleto: il file parziale è conservato per la ripresa.')
        print('Verifico l’integrità del modello…')
        if await asyncio.to_thread(file_hash, partial) != model['sha256']:
            partial.replace(partial.with_suffix('.invalid'))
            raise DownloadError('Checksum del modello non valido: il file non verrà utilizzato. Riprova il download.')
        validate_model(partial)
        partial.replace(target)
        return target


async def choose_model(root, override=None, model_name=None):
    if override:
        result = validate_model(parse_folder(str(override)))
        save_settings(root, model=str(result))
        return result
    if model_name:
        models = await model_catalog(root)
        model = next((m for m in models if m['name'] == model_name), None)
        if model is None:
            raise DownloadError('Modello non disponibile: %s' % model_name)
        result = await download_model(root, model)
        save_settings(root, model=str(result))
        return result
    settings = load_settings(root)
    saved = settings.get('model')
    while True:
        if saved and Path(saved).is_file():
            print('\nModello proposto: %s\n1) Usa questo modello\n2) Scarica un modello\n3) Indica il percorso di un modello GGML .bin\nq) Indietro' % saved)
            choice = (await ask('Scelta [1] > ')).strip().lower() or '1'
            action = {'1': 'saved', '2': 'download', '3': 'path'}.get(choice)
        else:
            print('\nModello Whisper\n1) Scarica un modello\n2) Indica il percorso di un modello GGML .bin già scaricato\nq) Indietro')
            choice = (await ask('Scelta [1] > ')).strip().lower() or '1'
            action = {'1': 'download', '2': 'path'}.get(choice)
        if choice == 'q':
            return None
        try:
            if action == 'saved':
                return validate_model(saved)
            if action == 'path':
                value = (await ask('Percorso del file modello (puoi trascinarlo dal Finder; q = indietro) > ')).strip()
                if value.lower() == 'q':
                    continue
                result = validate_model(parse_folder(value))
            elif action == 'download':
                models = await model_catalog(root)
                print('\nModelli disponibili: .en = solo inglese; q5/q8 = versioni più compatte.')
                for i, model in enumerate(models, 1):
                    suffix = ' · consigliato per iniziare' if model['name'] == 'small' else ''
                    if (Path(root) / 'modelli' / 'whisper' / model['filename']).exists():
                        suffix += ' · presente'
                    print('%d) %s · %.0f MB%s' % (i, model['name'], model['bytes'] / 1_000_000, suffix))
                value = (await ask('Numero del modello [1] · q = indietro > ')).strip().lower() or '1'
                if value == 'q':
                    continue
                if not value.isdigit() or not 1 <= int(value) <= len(models):
                    print('Numero non valido.')
                    continue
                result = await download_model(root, models[int(value) - 1])
            else:
                print('Scelta non valida.')
                continue
            save_settings(root, model=str(result))
            return result
        except (DownloadError, OSError, httpx.HTTPError) as exc:
            print('Modello non disponibile: %s' % (str(exc) if not isinstance(exc, httpx.HTTPError) else 'connessione interrotta; puoi riprovare per riprendere il download'))
