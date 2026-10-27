import os
import subprocess

from .config import data_root, load_config, project_root
from .ui import course_name


def main():
    os.umask(0o077)
    try:
        config = load_config()
        root = data_root()
        default = config.get('last_course') or ''
        print('\nPolimi Lectures\n')
        while True:
            prompt = 'Corso [%s]' % course_name(default) if default else 'Nome o codice del corso'
            query = input(prompt + ' · m = altre opzioni, q = esci\n> ').strip()
            if query.lower() == 'q':
                return 0
            if query.lower() in ('m', '/menu'):
                return subprocess.call(['bash', str(project_root() / 'Gestisci.command')])
            query = query or default
            if not query or (query.isdigit() and len(query) < 5):
                print('Scrivi il nome o il codice del corso, oppure premi Invio per quello proposto.')
                continue
            break
        from .cli import main as run
        os.environ['POLIMI_LECTURES_QUIET'] = '1'
        while True:
            print('\n1) Lezioni e materiali da WeBeep\n2) Trascrivi le lezioni scaricate\n3) Scegli il modello Whisper\n4) Associa slide e materiali alle lezioni\n5) Apri Trama · tutor interattivo\nq) Esci')
            operation = input('Operazione [1] > ').strip().lower() or '1'
            if operation == 'q':
                return 0
            if operation == '1':
                return run(['wizard', '--course', query])
            if operation == '2':
                run(['transcribe', '--course', query])
            elif operation == '3':
                run(['whisper-model'])
            elif operation == '4':
                run(['align', '--course', query])
            elif operation == '5':
                from .studio import main as study
                study()
            else:
                print('Scelta non valida.')
    except (OSError, ValueError) as exc:
        print('Non riesco ad avviare l’app: %s' % exc)
        input('Invio per chiudere ')
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nOperazione interrotta.')
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
