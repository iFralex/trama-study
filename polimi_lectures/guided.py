import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from .browser import ask, date_from_text
from .core import DownloadError, webex_id
from .ui import course_name, detail, lesson_name, show_date

COURSES = "https://webeep.polimi.it/my/courses.php"


def normalize(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def course_matches(query, label):
    requested_years = set(re.findall(r'\b20\d{2}\b', query))
    if requested_years:
        if not requested_years.issubset(set(re.findall(r'\b20\d{2}\b', label))):
            return False
        query = re.sub(r'\b20\d{2}(?:[-/]\d{2,4})?\b', '', query).strip()
        if not query:
            return True
    query, label = normalize(query), normalize(label)
    if not query:
        return False
    if query in label:
        return True
    words = label.split()
    width = len(query.split())
    return any(SequenceMatcher(None, query, ' '.join(words[i:i + width])).ratio() >= 0.82
               for i in range(max(1, len(words) - width + 1)))


async def course_links(page):
    links = await page.locator('a[href*="/course/view.php"]').evaluate_all('''els => els.map(el => ({
        url: el.href, text: (el.innerText || el.textContent || '').trim(), title: el.title || ''
    }))''')
    found = {}
    for link in links:
        parsed = urlsplit(link['url'])
        if parsed.hostname != 'webeep.polimi.it' or not parse_qs(parsed.query).get('id'):
            continue
        labels = [s for s in (link['text'], link['title']) if s]
        if not labels:
            continue
        label = max(labels, key=lambda s: (bool(re.search(r'\[20\d{2}[-/]\d{2,4}\]', s)), len(s)))
        key = parse_qs(parsed.query)['id'][0]
        old = found.get(key)
        if old is None or len(label) > len(old['label']):
            found[key] = {'url': link['url'], 'label': ' '.join(label.split())}
    return list(found.values())


async def login_and_courses(context, timeout=300):
    page = await context.new_page()
    await page.goto(COURSES, wait_until='domcontentloaded', timeout=45000)
    print('Verifico l’accesso a WeBeep…', flush=True)
    clicked = set()
    returned = False
    requested_login = False
    for _ in range(timeout * 2):
        for candidate in list(context.pages):
            if candidate.is_closed() or urlsplit(candidate.url).hostname != 'webeep.polimi.it':
                continue
            links = await course_links(candidate)
            if links:
                detail('Accesso a WeBeep disponibile.')
                return candidate, links
            if candidate.url not in clicked:
                login = candidate.get_by_role('link', name=re.compile(r'^Polimi login$', re.I))
                if await login.count() and await login.first.is_visible():
                    clicked.add(candidate.url)
                    try:
                        await login.first.click(timeout=5000)
                    except Exception:
                        print('Se compare un banner, chiudilo e premi Polimi login nel browser.', flush=True)
        if page.is_closed():
            raise DownloadError('La scheda di accesso è stata chiusa. Riapri il percorso guidato.')
        if urlsplit(page.url).hostname == 'servizionline.polimi.it' and not returned:
            returned = True
            await page.goto(COURSES, wait_until='domcontentloaded', timeout=45000)
        if not requested_login:
            host = urlsplit(page.url).hostname or ''
            if host == 'aunicalogin.polimi.it' or host == 'posteid.poste.it':
                if await page.locator('input[type="password"]:visible').count() or 'posteid.poste.it' == host:
                    print('Il portale richiede un nuovo accesso. Completa il login Polimi/SPID nel browser.', flush=True)
                    requested_login = True
        await page.wait_for_timeout(500)
    raise DownloadError('Accesso WeBeep non completato o elenco corsi non disponibile. HTML diagnostici salvati se attivi.')


async def choose_course(links, query):
    from .config import load_config, saved_course
    preferences = load_config()
    query = query or preferences.get('last_course', '')
    while True:
        saved = saved_course(preferences, query)
        candidates = [link for link in links if course_matches(query, link['label'])]
        for link in candidates:
            if link['label'] == saved.get('label') or (saved.get('url') and link['url'] == saved['url']):
                print('Corso: ' + course_name(link['label']))
                return link
        matches = [link for link in links if course_matches(query, link['label'])]
        if len(matches) == 1:
            print('Corso: ' + course_name(matches[0]['label']))
            return matches[0]
        if not matches:
            print('Nessun corso corrisponde a «%s».' % query)
            print('Corsi disponibili:\n' + '\n'.join('  ' + link['label'] for link in links))
            query = (await ask('Nome o codice del corso (q per uscire) > ')).strip()
            if query.lower() == 'q':
                raise DownloadError('Selezione del corso annullata.')
            continue
        print('Quale corso vuoi usare?')
        for i, link in enumerate(matches, 1):
            print('%d) %s' % (i, course_name(link['label'])))
        value = (await ask('Quale corso? Inserisci il numero > ')).strip()
        if value.isdigit() and 1 <= int(value) <= len(matches):
            return matches[int(value) - 1]
        print('Numero non valido.')


async def open_recordings(page, course):
    await page.goto(course['url'], wait_until='domcontentloaded', timeout=45000)
    print('Cerco le registrazioni…', flush=True)
    for _ in range(8):
        host = urlsplit(page.url).hostname or ''
        if host == 'onlineservices.polimi.it' and '/recman_frontend/' in page.url:
            await page.locator('a[title="Riproduci"]').first.wait_for(state='attached', timeout=20000)
            return page
        if host.endswith('.polimi.it') and host not in ('webeep.polimi.it', 'onlineservices.polimi.it'):
            # Il passaggio SSO dura normalmente pochi secondi. Attendi il redirect
            # invece di chiedere Invio mentre l'accesso sta già riuscendo.
            try:
                await page.wait_for_url(lambda url: urlsplit(str(url)).hostname in ('webeep.polimi.it', 'onlineservices.polimi.it'),
                                        timeout=10000, wait_until='domcontentloaded')
                continue
            except Exception:
                print('Per aprire l’archivio Polimi richiede un accesso nel browser. Proseguirò appena completato.', flush=True)
                try:
                    await page.wait_for_url(lambda url: urlsplit(str(url)).hostname in ('webeep.polimi.it', 'onlineservices.polimi.it'),
                                            timeout=300000, wait_until='domcontentloaded')
                    continue
                except Exception:
                    raise DownloadError('Accesso all’archivio non completato.') from None
        if host == 'webeep.polimi.it' and '/mod/url/view.php' in page.url:
            try:
                await page.wait_for_url(lambda url: '/mod/url/view.php' not in str(url), timeout=15000, wait_until='domcontentloaded')
                continue
            except Exception:
                pass
        if host == 'webeep.polimi.it':
            try:
                await page.locator('a[href*="/course/section.php"],a[href*="/mod/url/view.php"]').first.wait_for(state='attached', timeout=15000)
            except Exception:
                pass
            links = await page.locator('a[href]').evaluate_all('''els => els.map(el => ({
                url: el.href, text: (el.innerText || el.textContent || '').trim(), title: el.title || ''
            }))''')
            sections = [link for link in links if '/course/section.php' in link['url']
                        and re.fullmatch(r'(Vai alla sezione\s+)?Registrazioni', link['text'] or link['title'], re.I)]
            archives = [link for link in links if '/mod/url/view.php' in link['url']
                        and re.search(r'archivio\s+registrazioni', link['text'] + ' ' + link['title'], re.I)]
            # Il collegamento diretto all'archivio è spesso già nell'indice del corso.
            target = archives[0]['url'] if archives else (sections[0]['url'] if sections else None)
            if target:
                parsed = urlsplit(target)
                if parsed.hostname != 'webeep.polimi.it':
                    raise DownloadError('Collegamento registrazioni inatteso.')
                if '/mod/url/view.php' in parsed.path:
                    query = dict(parse_qsl(parsed.query))
                    query['redirect'] = '1'
                    target = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ''))
                await page.goto(target, wait_until='domcontentloaded', timeout=45000)
                continue
        raise DownloadError('Non trovo il collegamento all’archivio in questa pagina. Puoi usare la raccolta manuale nelle altre opzioni.')
    raise DownloadError('Archivio RecMan non raggiunto. Controlla gli HTML diagnostici della sessione.')


async def read_recordings(page):
    links = await page.locator('a[title="Riproduci"]').evaluate_all('''els => els.map(el => ({
        url: el.href, title: ((el.closest('tr') || el).innerText || '').trim()
    }))''')
    found = []
    for link in links:
        parsed = urlsplit(link['url'])
        if parsed.hostname != 'onlineservices.polimi.it' or '/recman_frontend/' not in parsed.path:
            continue
        found.append({'url': link['url'], 'title': ' '.join(link['title'].split()), 'date': date_from_text(link['title'])})
    return found


async def pagination_state(page):
    text = await page.locator('body').inner_text()
    match = re.search(r'pag\.\s*(\d+)\s*/\s*(\d+)\s*\(\s*totale\s*:\s*(\d+)\s*\)', text, re.I)
    return tuple(map(int, match.groups())) if match else None


async def save_listing(page):
    assistant = getattr(page.context, '_polimi_assistant', None)
    if assistant:
        await assistant.save_page(page)


async def navigate_listing(page, link):
    href = await link.get_attribute('href')
    if not href:
        raise DownloadError('Collegamento di paginazione privo di destinazione.')
    from urllib.parse import urljoin
    target = urljoin(page.url, href)
    parsed = urlsplit(target)
    if parsed.hostname != 'onlineservices.polimi.it' or '/recman_frontend/' not in parsed.path:
        raise DownloadError('Destinazione della paginazione RecMan inattesa.')
    try:
        await page.goto(target, wait_until='domcontentloaded', timeout=45000)
        await page.locator('a[title="Riproduci"]').first.wait_for(state='attached', timeout=20000)
    except Exception:
        raise DownloadError('RecMan non ha caricato le righe dopo il cambio pagina. La sessione potrebbe essere scaduta; HTML salvato.') from None
    finally:
        await save_listing(page)


async def all_recordings(page):
    await page.locator('a[title="Riproduci"]').first.wait_for(state='attached', timeout=20000)
    await save_listing(page)
    all_link = page.locator('a.paginator_link').filter(has_text=re.compile(r'^tutte$', re.I))
    if await all_link.count():
        detail('Carico tutte le registrazioni…')
        await navigate_listing(page, all_link.first)
    recordings, seen = [], set()
    expected = None
    for _ in range(100):
        batch = await read_recordings(page)
        state = await pagination_state(page)
        if state:
            current, pages, expected = state
            detail('RecMan: pagina %d/%d, %d righe (totale %d).' % (current, pages, len(batch), expected))
        # I parametri dei link cambiano a ogni richiesta: confronta le lezioni,
        # non i token/URL, per rilevare una pagina veramente ripetuta.
        fingerprint = tuple((record['date'], record['title']) for record in batch)
        if fingerprint in seen:
            await save_listing(page)
            raise DownloadError('RecMan ha restituito le stesse lezioni dopo il cambio pagina; raccolta incompleta. HTML diagnostico salvato.')
        seen.add(fingerprint)
        recordings.extend(batch)
        if state and current >= pages:
            break
        next_link = page.locator('a.paginator_link').filter(has_text=re.compile(r'^prossima$', re.I))
        if not await next_link.count():
            break
        await navigate_listing(page, next_link.first)
    else:
        raise DownloadError('Limite pagine raggiunto: raccolta incompleta.')
    if not recordings:
        raise DownloadError('Nessuna registrazione trovata per questo corso.')
    unique = {(record['date'], record['title']): record for record in recordings}
    if expected is not None and len(unique) != expected:
        raise DownloadError('Raccolte %d registrazioni su %d indicate da RecMan. Raccolta incompleta; controlla gli HTML diagnostici.' % (len(unique), expected))
    return sorted(unique.values(), key=lambda r: (r['date'] or '9999-12-31', r['title']))


def parse_date(value):
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError('Usa YYYY-MM-DD oppure gg/mm/aaaa.')


def in_range(recordings, start, end):
    return [record for record in recordings if record['date'] and
            (not start or record['date'] >= start) and (not end or record['date'] <= end)]


async def choose_recordings(recordings, state=None):
    dates = [record['date'] for record in recordings if record['date']]
    print('\n%d registrazioni%s' % (len(recordings), ' · %s – %s' % (show_date(min(dates)), show_date(max(dates))) if dates else ''))
    while True:
        print('1) Prova: scarica solo la prima lezione\n2) Scegli un intervallo di date\n3) Scarica tutte\n4) Materiali del corso\nq) Esci')
        choice = (await ask('Scelta [1] > ')).strip().lower() or '1'
        if choice == 'q':
            if state is not None:
                state['action'] = 'quit'
            return []
        if choice == '4':
            if state is not None:
                state['action'] = 'materials'
            return []
        if choice == '1':
            selected = recordings[:1]
        elif choice == '3':
            selected = recordings
        elif choice == '2':
            try:
                begin = (await ask('Dal giorno (gg/mm/aaaa o YYYY-MM-DD; Invio = senza limite) > ')).strip()
                end = (await ask('Al giorno (incluso; Invio = senza limite) > ')).strip()
                begin = parse_date(begin) if begin else None
                end = parse_date(end) if end else None
                if begin and end and begin > end:
                    raise ValueError('La data iniziale deve precedere quella finale.')
                selected = in_range(recordings, begin, end)
                if any(record['date'] is None for record in recordings):
                    print('Le registrazioni senza data sono escluse dal filtro.')
            except ValueError as exc:
                print(str(exc))
                continue
        else:
            print('Scelta non valida.')
            continue
        if not selected:
            print('Nessuna registrazione nell’intervallo. Scegli nuovamente.')
            continue
        if state is not None:
            state['action'] = 'recordings'
            state['test'] = choice == '1'
        print('\nSelezionata 1 registrazione:' if len(selected) == 1 else '\nSelezionate %d registrazioni:' % len(selected))
        for record in selected[:5]:
            print('  %s · %s' % (show_date(record['date']), lesson_name(record['title'])))
        if len(selected) > 5:
            print('  … e altre %d.' % (len(selected) - 5))
        return selected


async def recording_url(context, record):
    page = await context.new_page()
    urls = []
    def capture(request):
        if request.is_navigation_request() and webex_id(request.url):
            urls.append(request.url)
    page.on('request', capture)
    try:
        try:
            await page.goto(record['url'], wait_until='domcontentloaded', timeout=45000)
        except Exception:
            pass
        for _ in range(20):
            if webex_id(page.url):
                return page.url
            if urls:
                return urls[-1]
            await page.wait_for_timeout(500)
        raise DownloadError('Non riesco a ricavare il collegamento Webex della lezione: %s' % record['title'])
    finally:
        assistant = getattr(context, '_polimi_assistant', None)
        if assistant:
            await assistant.save_page(page)
        page.remove_listener('request', capture)
        await page.close()


async def selected_course(context, query):
    page, links = await login_and_courses(context)
    course = await choose_course(links, query)
    from .config import remember_course
    try:
        remember_course(course['label'], course['url'], query)
    except OSError:
        detail('Preferenza del corso non salvata; il download può proseguire.')
    return page, course


async def guided(context, catalog, query, state=None):
    state = state if state is not None else {}
    if not state.get('course'):
        page, course = await selected_course(context, query)
        state.update(page=page, course=course)
    else:
        page, course = state['page'], state['course']
    if not state.get('recordings'):
        await open_recordings(page, course)
        state['recordings'] = await all_recordings(page)
    selected = await choose_recordings(state['recordings'], state)
    ids = []
    for i, record in enumerate(selected, 1):
        detail('Risolvo il collegamento della registrazione %d/%d…' % (i, len(selected)))
        url = await recording_url(context, record)
        from .progress import recording_bytes
        catalog.add(course['label'], url, record['title'], record['date'], size_bytes=recording_bytes(record['title']))
        ids.append(webex_id(url))
    rows = {row['id']: row for row in catalog.rows(course['label'])}
    return [rows[rid] for rid in dict.fromkeys(ids)]
