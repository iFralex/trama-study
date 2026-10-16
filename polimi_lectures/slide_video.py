"""Timestamp-based video sampling, local boundary refinement and resumable exports."""
import csv
import hashlib
import io
import json
import math
from pathlib import Path

import av
import cv2
import numpy as np

from .local_jobs import atomic_bytes, atomic_json, file_hash, job_lock
from .slide_index import load_json, image_write, stat_key
from .slide_match import slide_rect, scan_signature, changed, PageMatcher, MATCH_VERSION

from .notebook_match import OCR_LAYOUT_VERSION, layout_is_clean

ALIGN_VERSION = 1
FRAME_SELECTION_VERSION = 2


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Video:
    def __init__(self, path):
        self.path = Path(path)
        self.container = av.open(str(path))
        self.stream = self.container.streams.video[0]
        self.stream.codec_context.thread_count = 2
        self.stream.thread_type = 'AUTO'
        self.origin = float(self.container.start_time or 0) / av.time_base
        if self.container.duration is not None:
            self.duration = float(self.container.duration) / av.time_base
        elif self.stream.duration is not None:
            self.duration = float(self.stream.duration * self.stream.time_base)
        else:
            raise ValueError('Durata video non disponibile.')

    def close(self):
        self.container.close()

    def frames(self, start, end):
        self.container.seek(int((start + self.origin) / self.stream.time_base), stream=self.stream, backward=True)
        for frame in self.container.decode(self.stream):
            if frame.pts is None:
                continue
            timestamp = float(frame.pts * frame.time_base) - self.origin
            if timestamp < start - .00001:
                continue
            if timestamp >= end:
                break
            yield timestamp, frame

    def snapshot(self, at):
        for timestamp, frame in self.frames(at, min(self.duration + .1, at + 15)):
            return timestamp, frame.to_ndarray(format='bgr24')
        raise ValueError('Nessun fotogramma al tempo %.3f.' % at)


def validate_scan(cache, run):
    if not isinstance(cache, dict) or 'events' not in cache:
        return False
    if cache.get('digest') != digest(cache['events']):
        return False
    return all((run / event['frame']).is_file() and (not event.get('frame_sha256') or file_hash(run / event['frame']) == event['frame_sha256']) for event in cache['events'])


def scan_window(video, start, end, step, run, rect=None):
    events = []
    anchor = None
    region = rect
    previous_time = start
    next_sample = start
    for timestamp, frame in video.frames(start, end):
        if timestamp + .00001 < next_sample:
            continue
        image = frame.to_ndarray(format='bgr24')
        next_sample = start + (math.floor((timestamp - start) / step) + 1) * step
        if anchor is None:
            region = rect or slide_rect(image)
        signature = scan_signature(image, region)
        if anchor is None or changed(anchor, signature):
            path = 'frames/%012d.png' % round(timestamp * 1000)
            image_write(run / path, image)
            events.append({'start': start if not events else timestamp,
                           'low': start if not events else previous_time, 'high': timestamp,
                           'frame_time': timestamp, 'frame': path, 'region': region, 'frame_sha256': file_hash(run / path)})
            region = rect or slide_rect(image)
            signature = scan_signature(image, region)
            events[-1]['region'] = region
            anchor = signature
        previous_time = timestamp
    if not events:
        raise ValueError('Nessun fotogramma nella finestra %.3f–%.3f.' % (start, end))
    return events


def refine_boundary(video, low, high, rect):
    if high <= low + .0001:
        return high, high - low
    _, left_image = video.snapshot(low)
    _, right_image = video.snapshot(high)
    left = scan_signature(left_image, rect).astype(np.float32)
    right = scan_signature(right_image, rect).astype(np.float32)
    separation = float(np.mean(np.abs(left - right)))
    if separation < 2:
        return high, high - low
    previous = low
    for timestamp, frame in video.frames(low, high + .15):
        current = scan_signature(frame.to_ndarray(format='bgr24'), rect).astype(np.float32)
        da = float(np.mean(np.abs(current - left)))
        db = float(np.mean(np.abs(current - right)))
        if db + .5 < da:
            return timestamp, max(.001, timestamp - previous)
        previous = timestamp
    return high, high - low



def interval_snapshot(video, start, end):
    # snapshot() returns the first PTS >= the requested timestamp; never allow it
    # to cross into the next scene, including variable-frame-rate recordings.
    at = (start + end) / 2
    try:
        timestamp, image = video.snapshot(at)
        if start <= timestamp < end:
            return timestamp, image
    except ValueError:
        pass
    candidate = None
    for timestamp, frame in video.frames(start, end):
        candidate = (timestamp, frame.to_ndarray(format='bgr24'))
        if timestamp >= at:
            break
    if candidate is None:
        raise ValueError('Nessun fotogramma nell’intervallo %.3f–%.3f.' % (start, end))
    return candidate

def material_key(recognition):
    if recognition.get('status') not in ('matched', 'document_only'):
        return None
    material = recognition['material']
    if material['kind'] == 'pdf':
        return ('pdf', material['page_id'])
    # Scrolling notebook screens are preserved as different events.
    return None


def merge_intervals(intervals):
    result = []
    for interval in intervals:
        key = material_key(interval)
        if result and key is not None and key == material_key(result[-1]) and abs(result[-1]['end'] - interval['start']) < .01:
            result[-1]['end'] = interval['end']
            result[-1]['end_uncertainty'] = interval['end_uncertainty']
            result[-1].setdefault('additional_frames', []).append(interval['frame'])
        else:
            result.append(interval.copy())
    return result


def transcript_segments(folder, video_sha):
    final = Path(folder) / 'trascrizione/trascrizione.json'
    if final.exists():
        data = load_json(final, {})
        if data.get('identity', {}).get('video_sha256') == video_sha and isinstance(data.get('segments'), list):
            return data['segments'], file_hash(final), 'complete'
    candidates = []
    for state in Path(folder).glob('trascrizione/sessioni/*/stato.json'):
        data = load_json(state, {})
        if data.get('identity', {}).get('video_sha256') == video_sha:
            candidates.append((data.get('completed_chunks', 0), state))
    if not candidates:
        return [], None, 'absent'
    _, state = max(candidates, key=lambda pair: pair[0])
    segments = []
    signatures = []
    for path in sorted((state.parent / 'blocchi').glob('*.json')):
        chunk = load_json(path, {})
        if isinstance(chunk.get('segments'), list) and chunk.get('sha256') == digest(chunk['segments']):
            segments.extend(chunk['segments'])
            signatures.append(chunk['sha256'])
    return segments, digest(signatures), 'partial'


def attach_transcript(intervals, segments):
    for interval in intervals:
        interval['transcript'] = [dict(segment, source_index=i,
                    overlap_start=max(segment['start'], interval['start']),
                    overlap_end=min(segment['end'], interval['end']))
                for i, segment in enumerate(segments)
                if segment['end'] > interval['start'] and segment['start'] < interval['end']]


def clock(seconds):
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return '%02d:%02d:%02d.%03d' % (hours, minutes, seconds, ms)


def export_alignment(directory, result):
    atomic_json(directory / 'allineamento.json', result)
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(['start_seconds', 'end_seconds', 'status', 'material', 'pdf_page', 'printed_number', 'confidence', 'frame', 'uncertainty_start', 'uncertainty_end'])
    lines = ['Allineamento dei materiali al video', '',
             'Intervallo analizzato: %s–%s. I tempi si riferiscono al video originale.' % (clock(result['scope']['start']), clock(result['scope']['end'])),
             'Matched = pagina riconosciuta; ambiguous = alternative irrisolte; document_only = notebook riconosciuto, celle candidate; unknown = nessuna corrispondenza.',
             'La precisione temporale riportata riguarda il confronto locale dei fotogrammi, non garantisce da sola l’identità corretta della pagina.',
             'Trascrizione disponibile: %s.' % result['transcript_state'], '',
             '| Da | A | Stato | Materiale | Pagina PDF | Qualità |',
             '|---|---|---|---|---:|---|']
    for interval in result['intervals']:
        material = interval.get('material') or {}
        name, page = material.get('file', ''), material.get('page', '')
        writer.writerow([interval['start'], interval['end'], interval['status'], name, page,
                         material.get('printed_number', ''), interval['confidence'], interval['frame'],
                         interval['start_uncertainty'], interval['end_uncertainty']])
        lines.append('| %s | %s | %s | %s | %s | %s |' % (clock(interval['start']), clock(interval['end']),
                     interval['status'], name.replace('|', ' '), page, interval['confidence']))
    lines += ['', 'I segmenti della trascrizione possono attraversare un cambio slide: il JSON conserva il testo originale e i tempi dell’intersezione, senza inventare tempi parola per parola.',
              'Le celle notebook elencate sono candidate OCR; il documento riconosciuto non implica che ogni cella candidata sia stata mostrata.',
              'Le alternative, le immagini di prova e il testo OCR sono nel JSON e nelle sessioni locali.', '']
    atomic_bytes(directory / 'allineamento.csv', stream.getvalue().encode('utf-8'))
    atomic_bytes(directory / 'allineamento.md', '\n'.join(lines).encode('utf-8'))


def align_video(video_path, output, index, index_directory, step=2.0, start=0.0, end=None, crop=None, pdf_filter=None, progress=print):
    if not math.isfinite(step) or not .2 <= step <= 10 or not math.isfinite(start) or (end is not None and not math.isfinite(end)):
        raise ValueError('Il campionamento deve essere tra 0.2 e 10 secondi.')
    output, video_path = Path(output), Path(video_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with job_lock(output / '.lock'):
        before = stat_key(video_path)
        video_sha = file_hash(video_path)
        video = Video(video_path)
        try:
            end = min(video.duration, end) if end is not None else video.duration
            if not 0 <= start < end:
                raise ValueError('Intervallo video non valido.')
            identity = {'version': ALIGN_VERSION, 'index': index['identity'], 'video_sha256': video_sha,
                        'step': step, 'scope': [start, end], 'crop': crop, 'pdf_filter': pdf_filter}
            signature = digest(identity)
            segments, transcript_signature, transcript_state = transcript_segments(video_path.parent, video_sha)
            marker = load_json(output / 'completo.json', {})
            if marker.get('identity') == identity and marker.get('transcript_signature') == transcript_signature and marker.get('recognition_version') == MATCH_VERSION and marker.get('ocr_layout_version') == OCR_LAYOUT_VERSION and marker.get('frame_selection_version') == FRAME_SELECTION_VERSION:
                hashes = marker.get('outputs', {})
                if set(hashes) == {'allineamento.json', 'allineamento.csv', 'allineamento.md'} and all(
                        (output / name).is_file() and file_hash(output / name) == checksum for name, checksum in hashes.items()):
                    progress('Allineamento già completo e verificato.')
                    return load_json(output / 'allineamento.json')
            run = output / 'sessioni' / signature[:24]
            (run / 'frames').mkdir(parents=True, exist_ok=True)
            (run / 'scansioni').mkdir(exist_ok=True)
            (run / 'riconoscimenti').mkdir(exist_ok=True)
            atomic_json(run / 'stato.json', {'identity': identity, 'phase': 'scan', 'video': str(video_path)})
            events = []
            window = start
            number = 0
            while window < end - .001:
                stop = min(end, window + 600)
                checkpoint = run / 'scansioni' / ('%05d.json' % number)
                cached = load_json(checkpoint)
                if not validate_scan(cached, run):
                    progress('Video · %s–%s' % (clock(window), clock(stop)))
                    current = scan_window(video, window, stop, step, run, crop)
                    cached = {'start': window, 'end': stop, 'events': current, 'digest': digest(current)}
                    atomic_json(checkpoint, cached)
                else:
                    progress('Ripresa · scansione %s già salvata' % clock(window))
                events.extend(cached['events'])
                window, number = stop, number + 1
            boundaries = [start]
            uncertainties = [0.0]
            boundary_path = run / 'confini.json'
            refined = load_json(boundary_path, [])
            for i, event in enumerate(events[1:], 1):
                if i == 1 or i % 20 == 0:
                    progress('Affino i confini temporali · %d/%d' % (i, len(events) - 1))
                key = digest({'event': event, 'previous': events[i - 1]})
                if i - 1 < len(refined) and refined[i - 1].get('key') == key:
                    value = refined[i - 1]
                else:
                    time, uncertainty = refine_boundary(video, event['low'], event['high'], events[i - 1]['region'])
                    value = {'key': key, 'time': time, 'uncertainty': uncertainty}
                    refined = refined[:i - 1] + [value]
                    atomic_json(boundary_path, refined)
                # A window start is a checkpoint boundary, not necessarily a scene cut.
                boundaries.append(max(boundaries[-1], min(end, value['time'])))
                uncertainties.append(value['uncertainty'])
            boundaries.append(end)
            uncertainties.append(0.0)
            matcher = PageMatcher(index, index_directory, pdf_filter)
            atomic_json(run / 'stato.json', {'identity': identity, 'phase': 'recognition', 'events': len(events)})
            recognitions = []
            for i, event in enumerate(events):
                next_start = events[i + 1]['start'] if i + 1 < len(events) else end
                checkpoint = run / 'riconoscimenti' / ('%05d.json' % i)
                cached = load_json(checkpoint)
                valid = bool(isinstance(cached, dict) and isinstance(cached.get('recognition'), dict) and cached.get('event_digest') == digest(event) and (run / cached.get('frame', '')).is_file())
                if valid and cached.get('recognition_digest'):
                    valid = cached['recognition_digest'] == digest(cached['recognition']) and cached.get('frame_sha256') == file_hash(run / cached['frame'])
                inside = bool(valid and boundaries[i] <= cached['frame_time'] < boundaries[i+1])
                notebook_data = cached['recognition'].get('notebook_ocr') if valid else None
                old_cells = (cached['recognition'].get('material') or {}).get('cells', []) if valid else []
                weak_notebook = bool(notebook_data and (not old_cells or old_cells[0]['score'] < .55
                    or (len(old_cells) > 1 and old_cells[0]['score'] - old_cells[1]['score'] < .12)))
                needs_frame_update = bool(valid and cached.get('frame_selection_version') != FRAME_SELECTION_VERSION
                    and (not inside or weak_notebook))
                reusable_frame = valid and inside and not needs_frame_update
                needs_title_update = bool(valid and cached.get('ocr_layout_version') != OCR_LAYOUT_VERSION
                    and cached['recognition'].get('status') == 'unknown'
                    and not cached['recognition'].get('notebook_ocr')
                    and 'ipynb' in cached['recognition'].get('ocr', '').casefold())
                valid = valid and cached.get('recognition_version') == MATCH_VERSION and layout_is_clean(cached['recognition']) and not needs_title_update and not needs_frame_update and inside
                if not valid:
                    progress('Riconosco schermata %d/%d · %s' % (i + 1, len(events), clock(event['start'])))
                    lo, hi = boundaries[i], boundaries[i+1]
                    if reusable_frame:
                        image = cv2.imread(str(run / cached['frame']))
                        actual = cached['frame_time']
                    else:
                        image = None
                    if image is None:
                        if hi - lo <= .001:
                            actual, image = video.snapshot(event['frame_time'])
                        else:
                            actual, image = interval_snapshot(video, lo, hi)
                    recognition = matcher.recognize(image, crop)
                    evidence = 'frames/riconoscimento-%05d.png' % i
                    image_write(run / evidence, image)
                    cached = {'event_digest': digest(event), 'recognition': recognition, 'recognition_version': MATCH_VERSION, 'ocr_layout_version': OCR_LAYOUT_VERSION, 'frame_selection_version': FRAME_SELECTION_VERSION,
                              'frame': evidence, 'frame_time': actual, 'recognition_digest': digest(recognition), 'frame_sha256': file_hash(run / evidence)}
                    atomic_json(checkpoint, cached)
                recognitions.append(cached)
            intervals = []
            for i, recognized in enumerate(recognitions):
                if boundaries[i + 1] - boundaries[i] <= .001:
                    continue
                intervals.append(dict(recognized['recognition'], start=round(boundaries[i], 6), end=round(boundaries[i + 1], 6),
                                      start_uncertainty=round(uncertainties[i], 6), end_uncertainty=round(uncertainties[i + 1], 6),
                                      frame=str((run / recognized['frame']).relative_to(output)), frame_time=recognized['frame_time']))
            intervals = merge_intervals(intervals)
            attach_transcript(intervals, segments)
            if stat_key(video_path) != before:
                raise ValueError('Il video è cambiato durante l’analisi; i risultati non sono segnati come completi.')
            result = {'identity': identity, 'recognition_version': MATCH_VERSION, 'ocr_layout_version': OCR_LAYOUT_VERSION, 'frame_selection_version': FRAME_SELECTION_VERSION, 'video': str(video_path), 'index': str(Path(index_directory) / 'index.json'),
                      'scope': {'start': start, 'end': end, 'full_video': start == 0 and end == video.duration},
                      'timeline_origin': video.origin, 'transcript_state': transcript_state,
                      'transcript_signature': transcript_signature, 'intervals': intervals,
                      'summary': {status: sum(interval['status'] == status for interval in intervals)
                                  for status in ('matched', 'ambiguous', 'document_only', 'unknown')}}
            export_alignment(output, result)
            names = ('allineamento.json', 'allineamento.csv', 'allineamento.md')
            atomic_json(output / 'completo.json', {'identity': identity, 'transcript_signature': transcript_signature,
                                                'recognition_version': MATCH_VERSION, 'ocr_layout_version': OCR_LAYOUT_VERSION, 'frame_selection_version': FRAME_SELECTION_VERSION, 'outputs': {name: file_hash(output / name) for name in names}})
            atomic_json(run / 'stato.json', {'identity': identity, 'phase': 'complete'})
            progress('Allineamento salvato: %s · %s' % (output, result['summary']))
            return result
        finally:
            video.close()
