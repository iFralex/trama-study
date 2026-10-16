"""Conservative page recognition from geometry and OCR."""
import collections
import math
from pathlib import Path

import cv2
import numpy as np

from .slide_index import features, phash, hash_distance, ocr, tokens

MATCH_VERSION = 2


def slide_rect(frame):
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    mask = (gray > 205).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, rw, rh = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if rw * rh > .22 * w * h and rh > .45 * h and .7 < rw / rh < 2.7 and area > .45 * rw * rh:
            candidates.append((area, [x, y, rw, rh]))
    return max(candidates, key=lambda value: value[0])[1] if candidates else [0, 0, w, h]


def crop_image(frame, rect=None, max_side=1100):
    x, y, w, h = rect or slide_rect(frame)
    x, y = max(0, int(x)), max(0, int(y))
    w, h = min(int(w), frame.shape[1] - x), min(int(h), frame.shape[0] - y)
    if w <= 0 or h <= 0:
        raise ValueError('Ritaglio video non valido.')
    crop = frame[y:y + h, x:x + w]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop.copy()
    scale = min(1.0, max_side / max(gray.shape)) if max_side else 1.0
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return gray


def scan_signature(frame, rect):
    gray = crop_image(frame, rect)
    # Most overlays are at the edges; stable content occupies the body.
    h, w = gray.shape
    body = gray[int(.12 * h):max(int(.94 * h), 1), int(.03 * w):max(int(.97 * w), 1)]
    return cv2.resize(body, (160, 100), interpolation=cv2.INTER_AREA)


def changed(a, b):
    diff = cv2.absdiff(a, b)
    fraction = float(np.mean(diff > 25))
    return float(np.mean(diff)) > 2.5 and fraction > .025


class TextIndex:
    def __init__(self, records, field='text'):
        self.records = records
        self.terms = [collections.Counter(tokens(record.get(field, ''))) for record in records]
        df = collections.Counter(word for terms in self.terms for word in terms)
        self.idf = {word: math.log(1 + (len(records) + 1) / (count + 1)) for word, count in df.items()}
        self.weights = [{word: (1 + math.log(count)) * self.idf[word] for word, count in terms.items()} for terms in self.terms]
        self.norms = [math.sqrt(sum(value * value for value in weights.values())) or 1 for weights in self.weights]

    def scores(self, text):
        terms = collections.Counter(tokens(text))
        weights = {word: (1 + math.log(count)) * self.idf[word] for word, count in terms.items() if word in self.idf}
        norm = math.sqrt(sum(value * value for value in weights.values())) or 1
        return [sum(value * weights.get(word, 0) for word, value in entry.items()) / (norm * length)
                for entry, length in zip(self.weights, self.norms)]


class PageMatcher:
    def __init__(self, index, directory, pdf_filter=None):
        self.directory = Path(directory)
        groups = {}
        for page in index['pages']:
            if pdf_filter and not any(page['file'] == name or Path(page['file']).name == name for name in pdf_filter):
                continue
            if page['id'] not in groups:
                groups[page['id']] = dict(page, aliases=[page['file']])
            elif page['file'] not in groups[page['id']]['aliases']:
                groups[page['id']]['aliases'].append(page['file'])
        self.pages = list(groups.values())
        if pdf_filter and not self.pages:
            raise ValueError('Nessun PDF corrisponde ai nomi richiesti.')
        self.text = TextIndex(self.pages)
        self.cells = index.get('cells', [])
        from .notebook_match import NotebookMatcher
        self.notebook = NotebookMatcher(self.cells)
        self.images, self.descriptors = collections.OrderedDict(), {}
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

    def visual_score(self, query, points, descriptors, page):
        if len(descriptors) < 12:
            return None
        ident = page['id']
        if ident not in self.descriptors:
            with np.load(self.directory / page['features'], allow_pickle=False) as data:
                self.descriptors[ident] = (data['points'].copy(), data['descriptors'].copy())
        source_points, source_desc = self.descriptors[ident]
        if len(source_desc) < 12:
            return None
        pairs = self.matcher.knnMatch(source_desc, descriptors, k=2)
        good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .75 * pair[1].distance]
        if len(good) < 12:
            return None
        source = np.float32([source_points[m.queryIdx] for m in good])
        target = np.float32([points[m.trainIdx] for m in good])
        matrix, mask = cv2.findHomography(source, target, cv2.RANSAC, 4)
        if matrix is None or mask is None or not np.all(np.isfinite(matrix)):
            return None
        inside = mask.flatten().astype(bool)
        inliers = int(np.sum(inside))
        if inliers < 12:
            return None
        hull = cv2.convexHull(source[inside])
        coverage = cv2.contourArea(hull) / (page['width'] * page['height'])
        if coverage < .06 or inliers / len(good) < .35:
            return None
        corners = np.float32([[0, 0], [page['width'], 0], [page['width'], page['height']], [0, page['height']]]).reshape(-1, 1, 2)
        projected = cv2.perspectiveTransform(corners, matrix)
        area = abs(cv2.contourArea(projected))
        if not cv2.isContourConvex(projected) or not .25 * query.size < area < 5 * query.size:
            return None
        if ident not in self.images:
            self.images[ident] = cv2.imread(str(self.directory / page['image']), cv2.IMREAD_GRAYSCALE)
        self.images.move_to_end(ident)
        original = self.images[ident]
        while len(self.images) > 32:
            self.images.popitem(last=False)
        if original is None:
            return None
        aligned = cv2.warpPerspective(original, matrix, (query.shape[1], query.shape[0]), borderValue=255)
        support = cv2.warpPerspective(np.full(original.shape, 255, np.uint8), matrix, (query.shape[1], query.shape[0]))
        support = cv2.erode(support, np.ones((9, 9), np.uint8)) > 200
        left = (cv2.Canny(aligned, 70, 170) > 0) & support
        right = (cv2.Canny(query, 70, 170) > 0) & support
        kernel = np.ones((5, 5), np.uint8)
        left_near = cv2.dilate(left.astype(np.uint8), kernel) > 0
        right_near = cv2.dilate(right.astype(np.uint8), kernel) > 0
        precision = float(np.sum(right & left_near)) / max(1, np.sum(right))
        recall = float(np.sum(left & right_near)) / max(1, np.sum(left))
        similarity = 2 * precision * recall / max(.001, precision + recall)
        score = .75 * similarity + .25 * min(1, inliers / 70)
        return {'visual': round(score, 4), 'edge_similarity': round(similarity, 4), 'inliers': inliers,
                'coverage': round(coverage, 4), 'homography': matrix.tolist()}

    def recognize(self, frame, rect=None):
        region = rect or slide_rect(frame)
        query = crop_image(frame, region)
        from .notebook_match import ocr_layout
        raw = crop_image(frame, region, max_side=None)
        layout = ocr_layout(raw)
        text = layout["text"]
        fingerprint = phash(query)
        points, descriptors = features(query)
        text_scores = self.text.scores(text)
        ranks = sorted(range(len(self.pages)), key=lambda i: text_scores[i], reverse=True)[:14]
        ranks += sorted(range(len(self.pages)), key=lambda i: hash_distance(fingerprint, self.pages[i]['phash']))[:12]
        candidates = []
        for i in dict.fromkeys(ranks):
            page = self.pages[i]
            evidence = self.visual_score(query, points, descriptors, page)
            if evidence is None:
                continue
            similarity = 1 - hash_distance(fingerprint, page['phash']) / 64
            score = .65 * evidence['visual'] + .30 * text_scores[i] + .05 * similarity
            candidates.append({'kind': 'pdf', 'page_id': page['id'], 'file': page['file'], 'aliases': page['aliases'],
                               'page': page['page'], 'printed_number': page.get('printed_number'), 'content_key': page['content_key'],
                               'score': round(score, 4), 'text_score': round(text_scores[i], 4), **evidence})
        candidates.sort(key=lambda item: item['score'], reverse=True)
        base = {'region': region, 'ocr': text, 'phash': fingerprint, 'candidates': candidates[:4], 'ocr_mode': 'native', 'ocr_image_size': [raw.shape[1], raw.shape[0]], 'recognition_version': MATCH_VERSION}
        if candidates:
            best = candidates[0]
            margin = best['score'] - candidates[1]['score'] if len(candidates) > 1 else best['score']
            acceptable = best['score'] >= .55 and best['visual'] >= .53 and best['edge_similarity'] >= .38
            if acceptable:
                alternatives = [item for item in candidates[1:] if best['score'] - item['score'] < .06]
                equivalent = alternatives and all(item['content_key'] == best['content_key'] for item in alternatives)
                if margin >= .06 or equivalent:
                    return dict(base, status='matched', material=best, alternatives=alternatives, margin=round(margin, 4),
                                confidence='high' if best['score'] >= .72 and margin >= .08 else 'medium')
                return dict(base, status='ambiguous', material=None, alternatives=[best] + alternatives, confidence='unresolved')
        # Read the active notebook title and body at the source resolution.
        full_region = rect or [0, 0, frame.shape[1], frame.shape[0]]
        full = crop_image(frame, full_region, max_side=None)
        if full.shape != raw.shape or full_region != region:
            layout = ocr_layout(full)
        notebook = self.notebook.recognize(full, layout)
        if notebook is not None:
            return dict(base, **notebook)
        return dict(base, status='unknown', material=None, confidence='unresolved', reason='Nessuna corrispondenza sufficientemente solida.')
