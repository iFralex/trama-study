"""Native-resolution notebook OCR and conservative cell candidates."""
import collections
import csv
import io
import re
import subprocess
from pathlib import Path

import cv2

from .slide_index import ocr, tokens

OCR_LAYOUT_VERSION = 3


def layout_is_clean(recognition):
    texts = [recognition.get("ocr", ""), (recognition.get("notebook_ocr") or {}).get("text", "")]
    return all("\t" not in text for text in texts)


def ocr_layout(gray):
    success, encoded = cv2.imencode('.png', gray)
    if not success:
        raise ValueError('Immagine OCR non valida.')
    result = subprocess.run(
        ['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', '11', 'tsv'],
        input=encoded.tobytes(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=60, check=True)
    groups = collections.OrderedDict()
    for word in csv.DictReader(io.StringIO(result.stdout.decode('utf-8', 'replace')), delimiter='\t', quoting=csv.QUOTE_NONE):
        text = (word.get('text') or '').strip()
        if word.get('level') != '5' or not text:
            continue
        key = tuple(word[field] for field in ('block_num', 'par_num', 'line_num'))
        x, y, w, h = [int(word[field]) for field in ('left', 'top', 'width', 'height')]
        line = groups.setdefault(key, {'words': [], 'left': x, 'top': y, 'right': x+w, 'bottom': y+h})
        line['words'].append(text)
        line['left'], line['top'] = min(line['left'], x), min(line['top'], y)
        line['right'], line['bottom'] = max(line['right'], x+w), max(line['bottom'], y+h)
    lines = [dict(line, text=' '.join(line['words'])) for line in groups.values()]
    return {'text': '\n'.join(line['text'] for line in lines), 'lines': lines}


def visible_source(source):
    source = re.sub(r'<!--[\s\S]*?-->', ' ', source)
    source = re.sub(r'<br\s*/?>', '\n', source, flags=re.I)
    source = re.sub(r'<(?:img|a)\b[^>]*>', ' ', source, flags=re.I)
    source = re.sub(r'</a>', '', source, flags=re.I)
    source = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', source)
    return re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', source)


def normalized_filename(name):
    return re.sub(r'[^a-z0-9]', '', name.casefold())


def notebook_view(layout, width, height):
    """Prefer the document title near the toolbar over browser tab captions."""
    filenames, toolbars = [], []
    for line in layout['lines']:
        if line['top'] > .40 * height:
            continue
        compact = ''.join(line['words'])
        matches = re.findall(r'[a-zA-Z0-9_.-]+\.?ipynb\b', line['text'], flags=re.I)
        if not matches:
            matches = re.findall(r'[a-zA-Z0-9_.-]+\.?ipynb\b', compact, flags=re.I)
        for name in matches:
            filenames.append((line['bottom'], name, line))
        terms = set(tokens(line['text']))
        if ({'codice', 'testo'} <= terms or {'code', 'text'} <= terms):
            toolbars.append(line)
    if not filenames:
        return None
    if toolbars:
        toolbar = max(toolbars, key=lambda line: line['bottom'])
        above = [entry for entry in filenames if entry[0] <= toolbar['top']]
        if not above:
            return None
        _, name, title = max(above, key=lambda entry: entry[0])
        top = toolbar['bottom'] + 5
    else:
        _, name, title = max(filenames, key=lambda entry: entry[0])
        top = title['bottom'] + max(25, 3 * (title['bottom'] - title['top']))
    left = int(.04 * width)
    right, bottom = int(.96 * width), int(.95 * height)
    if top >= bottom:
        return None
    return {'filename': name, 'region': [left, top, right-left, bottom-top]}


class NotebookMatcher:
    def __init__(self, cells):
        from .slide_match import TextIndex
        self.documents = {}
        for cell in cells:
            doc = self.documents.setdefault(cell['file_id'], {'file': cell['file'], 'cells': []})
            doc['cells'].append(dict(cell, visible=visible_source(cell['source'])))
        for doc in self.documents.values():
            doc['index'] = TextIndex([dict(cell, text=cell['visible']) for cell in doc['cells']])

    def recognize(self, gray, layout):
        h, w = gray.shape
        view = notebook_view(layout, w, h)
        if view is None:
            return None
        matches = [(ident, doc) for ident, doc in self.documents.items()
                   if normalized_filename(Path(doc['file']).name) == normalized_filename(view['filename'])]
        if len(matches) != 1:
            return {'status': 'unknown', 'material': None, 'confidence': 'unresolved',
                    'reason': 'Notebook visibile non presente nell’indice oppure nome ambiguo.',
                    'notebook_ocr': dict(view, mode='native', source_size=[w, h], indexed=False)}
        ident, doc = matches[0]
        x, y, rw, rh = view['region']
        body = gray[y:y+rh, x:x+rw]
        text = ocr(body)
        scores = doc['index'].scores(text)
        query_terms = set(tokens(text))
        candidates = []
        for cell, score in zip(doc['cells'], scores):
            overlap = len(query_terms & set(tokens(cell['visible'])))
            if score >= .25 and overlap >= 4:
                candidates.append({'cell_index': cell['cell_index'], 'cell_id': cell['cell_id'],
                                   'kind': cell['kind'], 'score': round(score, 4), 'matched_terms': overlap})
        candidates.sort(key=lambda item: item['score'], reverse=True)
        return {'status': 'document_only', 'material': {'kind': 'notebook', 'file_id': ident,
                'file': doc['file'], 'cells': candidates[:4]}, 'confidence': 'medium',
                'reason': 'Titolo notebook visibile; OCR nativo del contenuto. Le celle restano candidate.',
                'notebook_ocr': dict(view, mode='native', source_size=[w, h],
                                     image_size=[body.shape[1], body.shape[0]], text=text, indexed=True)}
