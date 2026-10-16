"""Material index and image features; no notebook code is executed."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pymupdf

from .local_jobs import atomic_json, file_hash, job_lock

INDEX_VERSION = 1


def tokens(value):
    return re.findall(r'[a-z0-9_]{2,}', value.casefold())


def phash(gray):
    small = cv2.resize(gray, (32, 32)).astype(np.float32)
    values = cv2.dct(small)[:8, :8].flatten()
    bits = values > np.median(values[1:])
    return ''.join('%02x' % byte for byte in np.packbits(bits))


def hash_distance(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count('1')


def features(gray):
    orb = cv2.ORB_create(nfeatures=2200, fastThreshold=12)
    points, descriptors = orb.detectAndCompute(gray, None)
    coordinates = np.array([point.pt for point in points], dtype=np.float32).reshape(-1, 2)
    if descriptors is None:
        descriptors = np.empty((0, 32), dtype=np.uint8)
    return coordinates, descriptors


def image_write(path, gray):
    success, encoded = cv2.imencode('.png', gray)
    if not success:
        raise ValueError('Impossibile salvare il fotogramma.')
    from .local_jobs import atomic_bytes
    atomic_bytes(path, encoded.tobytes())


def ocr(gray):
    success, encoded = cv2.imencode('.png', gray)
    if not success:
        raise ValueError('Immagine OCR non valida.')
    result = subprocess.run(['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', '11'],
                            input=encoded.tobytes(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=60, check=True)
    return result.stdout.decode('utf-8', 'replace').strip()


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def stat_key(path):
    value = Path(path).stat()
    return {'bytes': value.st_size, 'mtime_ns': value.st_mtime_ns}


def content_key(text, image_hash):
    # Page numbers are excluded so identical content can have several sources.
    lines = [line.strip().casefold() for line in text.splitlines() if line.strip() and not re.fullmatch(r'\d{1,4}', line.strip())]
    return hashlib.sha256((' '.join(lines) + image_hash).encode()).hexdigest()


def index_materials(materials, output, progress=print):
    materials, output = Path(materials).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with job_lock(output / '.lock'):
        previous = load_json(output / 'index.json', {})
        old_files = {item['path']: item for item in previous.get('files', [])}
        files, pages, cells, issues = [], [], [], []
        supported = sorted(path for path in materials.rglob('*') if path.is_file() and path.suffix.lower() in ('.pdf', '.ipynb'))
        for number, path in enumerate(supported, 1):
            relative = str(path.relative_to(materials))
            before = stat_key(path)
            old = old_files.get(relative, {})
            digest = old.get('sha256') if old.get('stat') == before else file_hash(path)
            if stat_key(path) != before:
                raise ValueError('Materiale cambiato durante la lettura: ' + relative)
            file_id = digest[:24]
            document = output / 'documenti' / file_id
            document.mkdir(parents=True, exist_ok=True)
            entry = {'id': file_id, 'path': relative, 'sha256': digest, 'stat': before, 'kind': path.suffix.lower()[1:]}
            files.append(entry)
            progress('Indice %d/%d · %s' % (number, len(supported), relative))
            try:
                if path.suffix.lower() == '.ipynb':
                    notebook = json.loads(path.read_text(encoding='utf-8'))
                    if notebook.get('nbformat') != 4 or not isinstance(notebook.get('cells'), list):
                        raise ValueError('Formato notebook non supportato.')
                    for i, cell in enumerate(notebook['cells']):
                        source = cell.get('source', '')
                        source = ''.join(source) if isinstance(source, list) else source
                        if not isinstance(source, str):
                            raise ValueError('Cella notebook non valida.')
                        outputs = []
                        for value in cell.get('outputs', []):
                            text = value.get('text', value.get('data', {}).get('text/plain', ''))
                            outputs.append(''.join(text) if isinstance(text, list) else str(text))
                        cells.append({'id': file_id + ':cell:' + str(i), 'file_id': file_id, 'file': relative,
                                      'cell_index': i, 'cell_id': cell.get('id'), 'kind': cell.get('cell_type'),
                                      'source': source, 'output_text': '\n'.join(outputs)[:5000]})
                    if stat_key(path) != before:
                        raise ValueError('Notebook cambiato durante l’indicizzazione.')
                    continue
                with pymupdf.open(path) as pdf:
                    for i, page in enumerate(pdf):
                        record_path = document / ('%05d.json' % (i + 1))
                        image_path = document / ('%05d.png' % (i + 1))
                        feature_path = document / ('%05d.npz' % (i + 1))
                        cached = load_json(record_path)
                        valid = bool(cached and cached.get('version') == INDEX_VERSION and image_path.is_file() and feature_path.is_file())
                        if valid and cached.get('cache_hashes'):
                            valid = cached['cache_hashes'] == {'image': file_hash(image_path), 'features': file_hash(feature_path)}
                        if not valid:
                            zoom = 1100 / max(page.rect.width, page.rect.height)
                            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY, alpha=False)
                            gray = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width).copy()
                            text = page.get_text('text', sort=True).strip()
                            blocks = [{'bbox': list(b[:4]), 'text': b[4]} for b in page.get_text('blocks') if b[6] == 0]
                            source = 'native'
                            if len(tokens(text)) < 6:
                                text = ocr(gray)
                                source = 'ocr'
                            points, descriptors = features(gray)
                            image_write(image_path, gray)
                            temporary = feature_path.with_suffix('.tmp.npz')
                            np.savez_compressed(temporary, points=points, descriptors=descriptors)
                            temporary.replace(feature_path)
                            body = gray[:int(gray.shape[0] * .93)]
                            fingerprint = phash(gray)
                            lines = text.splitlines()
                            footer = next((int(line.strip()) for line in reversed(lines[-5:]) if re.fullmatch(r'\d{1,4}', line.strip())), None)
                            cached = {'version': INDEX_VERSION, 'id': file_id + ':page:' + str(i + 1), 'file_id': file_id,
                                      'page': i + 1, 'printed_number': footer, 'width': gray.shape[1], 'height': gray.shape[0],
                                      'text': text, 'text_source': source, 'text_blocks': blocks, 'phash': fingerprint,
                                      'content_key': content_key(text, phash(body)), 'image': str(image_path.relative_to(output)),
                                      'features': str(feature_path.relative_to(output))}
                            atomic_json(record_path, cached)
                        hashes = {'image': file_hash(image_path), 'features': file_hash(feature_path)}
                        if cached.get('cache_hashes') != hashes:
                            cached['cache_hashes'] = hashes
                            atomic_json(record_path, cached)
                        pages.append(dict(cached, file=relative))
                if stat_key(path) != before:
                    raise ValueError('PDF cambiato durante l’indicizzazione.')
            except (ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                issues.append({'file': relative, 'error': str(exc)[:300]})
        identity = hashlib.sha256(json.dumps([(f['path'], f['sha256']) for f in files], sort_keys=True).encode()).hexdigest()
        index = {'version': INDEX_VERSION, 'materials': str(materials), 'identity': identity,
                 'files': files, 'pages': pages, 'cells': cells, 'issues': issues}
        atomic_json(output / 'index.json', index)
        progress('Indice pronto: %d pagine PDF, %d celle, %d problemi.' % (len(pages), len(cells), len(issues)))
        return index
