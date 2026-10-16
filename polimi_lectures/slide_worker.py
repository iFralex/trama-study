"""Native worker: deliberately imports no browser or transcription dependencies."""
import argparse
import json
import sys
import subprocess
from pathlib import Path

from .slide_index import index_materials
from .slide_video import align_video
from .local_jobs import atomic_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    args = parser.parse_args(argv)
    request = json.loads(args.request.read_text(encoding='utf-8'))
    progress = lambda message: print(message, flush=True)
    index = index_materials(request['materials'], request['index'], progress)
    failures = []
    for i, item in enumerate(request['items'], 1):
        progress('\n[%d/%d] %s' % (i, len(request['items']), Path(item['video']).parent.name))
        try:
            align_video(item['video'], item['output'], index, request['index'],
                        progress=progress, **request.get('options', {}))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            failures.append({'video': item['video'], 'error': str(exc)})
            progress('Non completato: %s. I checkpoint salvati restano disponibili.' % exc)
    atomic_json(args.request.with_suffix('.risultato.json'), {'failures': failures, 'index_issues': index['issues']})
    if index['issues']:
        progress('Attenzione: %d materiali non indicizzati completamente; dettagli in index.json.' % len(index['issues']))
    return int(bool(failures or index['issues']))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nInterrotto: i checkpoint già completati sono conservati.', flush=True)
        sys.exit(130)
