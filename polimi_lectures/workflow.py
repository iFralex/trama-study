import subprocess

from .browser import ask
from .core import DownloadError
from .guided import guided, selected_course
from .ui import lesson_name, show_date


def delete_test_video(catalog, rows):
    removed = 0
    for original in rows:
        row = next((r for r in catalog.rows(original['course']) if r['id'] == original['id']), None)
        if row is None:
            continue
        folder = catalog.folder(row).resolve()
        if catalog.root.resolve() not in folder.parents:
            raise DownloadError('Percorso del video esterno all’archivio: eliminazione interrotta.')
        video = folder / 'video.mp4'
        if video.is_symlink():
            raise DownloadError('Il video è un collegamento: eliminazione interrotta.')
        if video.is_file():
            video.unlink()
            (folder / 'metadata.json').unlink(missing_ok=True)
            catalog.update(row, 'pending')
            removed += 1
        # Lascia intatti trascrizioni, appunti e altri file eventualmente presenti.
    return removed


async def download_rows(context, catalog, rows):
    from .cli import download_one
    from .progress import BatchProgress
    batch = BatchProgress(rows)
    if rows:
        print('  ' + batch.text())
    downloaded = present = failed = 0
    for i, row in enumerate(rows, 1):
        print('\n[%d/%d] %s · %s' % (i, len(rows), show_date(row['date']), lesson_name(row['title'])))
        try:
            batch.start(row)
            outcome = await download_one(context, catalog, row, batch=batch)
            batch.finish((catalog.folder(row) / 'video.mp4').stat().st_size)
            print('  ' + batch.text())
            downloaded += outcome == 'downloaded'
            present += outcome == 'present'
        except Exception as exc:
            failed += 1
            reason = str(exc) if isinstance(exc, DownloadError) else 'Errore %s; puoi riprovare.' % type(exc).__name__
            catalog.update(row, 'error', error=reason)
            print('  Non riuscito: ' + reason)
    if rows:
        print('\n%s · %d %s, %d già %s%s.' %
              ('Completato' if not failed else 'Terminato', downloaded, 'scaricata' if downloaded == 1 else 'scaricate',
               present, 'presente' if present == 1 else 'presenti', ', %d non riuscite' % failed if failed else ''))
        fresh = next((r for r in catalog.rows(rows[0]['course']) if r['id'] == rows[0]['id']), rows[0])
        print('Cartella: %s' % (catalog.folder(fresh) if len(rows) == 1 else catalog.root / 'corsi'))
    return failed


async def course_workflow(context, catalog, query, materials_first=False):
    from .materials import download_materials
    state = {}
    action = 'materials' if materials_first else 'recordings'
    failures = 0
    while True:
        try:
            if action == 'recordings':
                rows = await guided(context, catalog, query, state)
                if state.get('action') == 'quit':
                    return int(bool(failures))
                if state.get('action') == 'materials':
                    await download_materials(context, catalog, state['course'])
                else:
                    failures += await download_rows(context, catalog, rows)
                    if state.get('test') and rows:
                        state['test_rows'] = rows
            elif action == 'materials':
                if not state.get('course'):
                    page, course = await selected_course(context, query)
                    state.update(page=page, course=course)
                await download_materials(context, catalog, state['course'])
            elif action == 'transcribe':
                from .transcribe import transcribe_course
                failures += await transcribe_course(catalog, state['course']['label'] if state.get('course') else query)
            elif action == 'align':
                from .alignment import align_course
                failures += await align_course(catalog, state['course']['label'] if state.get('course') else query)
        except Exception as exc:
            failures += 1
            reason = str(exc) if isinstance(exc, DownloadError) else 'Operazione non completata (%s). Puoi riprovare o scegliere un’altra azione.' % type(exc).__name__
            print('Non completato: %s' % reason)
        while True:
            print('\nCosa vuoi fare adesso?\n1) Scarica altre lezioni\n2) Scarica materiali del corso')
            if state.get('test_rows'):
                print('3) Elimina il video di prova · %s' % show_date(state['test_rows'][0]['date']))
            print('4) Apri la cartella dei corsi\n5) Cambia corso\n6) Trascrivi le lezioni scaricate\n7) Associa slide e materiali alle lezioni\nq) Esci')
            value = (await ask('Scelta > ')).strip().lower()
            if value == 'q':
                return int(bool(failures))
            if value == '1':
                action = 'recordings'
                break
            if value == '2':
                action = 'materials'
                break
            if value == '6':
                action = 'transcribe'
                break
            if value == '7':
                action = 'align'
                break
            if value == '3' and state.get('test_rows'):
                try:
                    count = delete_test_video(catalog, state['test_rows'])
                    state.pop('test_rows', None)
                    print('Video di prova eliminato.' if count else 'Il video di prova non è presente.')
                except (DownloadError, OSError) as exc:
                    print('Eliminazione non riuscita: %s' % exc)
            elif value == '4':
                folder = catalog.root / 'corsi'
                if folder.exists():
                    subprocess.run(['open', str(folder)], check=False)
                else:
                    print('Nessun file salvato per il momento.')
            elif value == '5':
                query = (await ask('Nome del corso (aggiungi l’anno per cambiarlo) > ')).strip()
                if query:
                    state, action = {}, 'recordings'
                    break
