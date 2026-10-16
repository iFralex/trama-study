import hashlib
import html
import json
import mimetypes
import re
from email.message import Message
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

from .browser import ask
from .core import DownloadError, slug
from .guided import save_listing


def source_key(url):
    parsed = urlsplit(url)
    ident = parse_qs(parsed.query).get('id', [])
    query = 'id=' + ident[0] if ident and ident[0].isdigit() else ''
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ''))


def safe_name(value):
    value = re.sub(r'[/\\:\x00-\x1f]', '_', unquote(value)).strip().strip('.')
    return value[:160] or 'file'


def selection_numbers(value, count):
    selected = set()
    for item in value.replace(' ', '').split(','):
        bounds = item.split('-')
        if len(bounds) not in (1, 2) or any(not b.isdigit() for b in bounds):
            raise ValueError('Usa numeri e intervalli, per esempio 1,3,5-8.')
        first, last = int(bounds[0]), int(bounds[-1])
        if first < 1 or last > count or first > last:
            raise ValueError('Numero o intervallo fuori dall’elenco.')
        selected.update(range(first - 1, last))
    return sorted(selected)


async def page_links(page):
    scope = page.locator('#region-main')
    if not await scope.count():
        scope = page.locator('main, [role="main"]').first
    if not await scope.count():
        scope = page.locator('body')
    return await scope.locator('a[href], object[data], embed[src], iframe[src]').evaluate_all('''els => els.map(el => ({
        url: el.href || el.data || el.src || '',
        label: (el.innerText || el.textContent || el.title || '').trim()
    }))''')


def file_asset(link, group, module_id):
    parsed = urlsplit(link['url'])
    if parsed.hostname != 'webeep.polimi.it' or '/pluginfile.php/' not in parsed.path:
        return None
    if not re.search(r'/mod_(folder|resource|page|label)/', parsed.path):
        return None
    name = unquote(parsed.path.rsplit('/', 1)[-1])
    if not name:
        return None
    if '/mod_label/' in parsed.path and not re.search(r'\.(pdf|zip|7z|tar|gz|pptx?|docx?|xlsx?|txt|csv|ipynb|py|c|cpp|h|cu|html?)$', name, re.I):
        return None
    folder_path = re.search(r'/mod_folder/content/\d+/(.+)$', parsed.path)
    relative = folder_path[1] if folder_path else name
    return {'kind': 'file', 'url': link['url'], 'name': unquote(relative), 'group': group, 'module_id': module_id,
            'relative': relative}


async def discover_materials(context, course):
    page = await context.new_page()
    found, modules, issues = {}, {}, []
    try:
        print('Cerco i materiali su WeBeep…', flush=True)
        await page.goto(course['url'], wait_until='domcontentloaded', timeout=45000)
        if urlsplit(page.url).hostname != 'webeep.polimi.it' or '/login/' in page.url:
            raise DownloadError('WeBeep richiede un nuovo accesso prima di leggere i materiali.')
        def collect(links):
            for link in links:
                parsed = urlsplit(link['url'])
                ids = parse_qs(parsed.query).get('id', [])
                if parsed.hostname == 'webeep.polimi.it' and re.fullmatch(r'/mod/(folder|resource|page)/view\.php', parsed.path) and ids and ids[0].isdigit():
                    key = source_key(link['url'])
                    label = re.sub(r'\s+(Cartella|File|Pagina)$', '', link['label'], flags=re.I).strip()
                    if key not in modules or (label and modules[key]['label'].startswith('Materiale ')):
                        modules[key] = {'url': link['url'], 'label': label or ('Materiale ' + ids[0]), 'id': ids[0],
                                        'kind': parsed.path.split('/')[2]}
                asset = file_asset(link, 'Materiali', 'corso')
                if asset:
                    found[source_key(asset['url'])] = asset

        links = await page_links(page)
        collect(links)
        await save_listing(page)
        # Moodle può mostrare solo le schede delle sezioni nell'indice del corso.
        # Visitiamo quelle del contenuto principale, senza seguire altri corsi.
        sections = {}
        course_id = parse_qs(urlsplit(course['url']).query).get('id')
        for link in links:
            parsed = urlsplit(link['url'])
            params = parse_qs(parsed.query)
            if parsed.hostname != 'webeep.polimi.it':
                continue
            if (parsed.path == '/course/section.php' and params.get('id')) or (
                    parsed.path == '/course/view.php' and params.get('id') == course_id and params.get('section')):
                # Con section= l'id del corso da solo non identifica la sezione.
                key = (parsed.path, tuple(params.get('id', [])), tuple(params.get('section', [])))
                sections[key] = link
        for section in sections.values():
            try:
                await page.goto(section['url'], wait_until='domcontentloaded', timeout=45000)
                if urlsplit(page.url).hostname != 'webeep.polimi.it' or '/login/' in page.url:
                    raise DownloadError('Sessione WeBeep non disponibile.')
                collect(await page_links(page))
            except Exception as exc:
                issues.append((section['label'] or 'Sezione') + ': ' + (str(exc) if isinstance(exc, DownloadError) else 'pagina non leggibile'))
            finally:
                await save_listing(page)
        for module in modules.values():
            if module['kind'] == 'resource':
                # Il modulo può rispondere direttamente con PDF/ZIP e Content-Disposition.
                asset = {'kind': 'file', 'url': module['url'] + ('&' if '?' in module['url'] else '?') + 'redirect=1',
                         'name': module['label'], 'group': module['label'], 'module_id': module['id'], 'relative': None}
                found[source_key(asset['url'])] = asset
                continue
            try:
                await page.goto(module['url'], wait_until='domcontentloaded', timeout=45000)
                if '/login/' in page.url or urlsplit(page.url).hostname != 'webeep.polimi.it':
                    raise DownloadError('Sessione WeBeep non disponibile.')
                await page.wait_for_timeout(400)
                for _ in range(30):
                    collapsed = page.locator('.foldertree [aria-expanded="false"], .filemanager [aria-expanded="false"]')
                    if not await collapsed.count():
                        break
                    try:
                        await collapsed.first.click(timeout=1000)
                        await page.wait_for_timeout(100)
                    except Exception:
                        break
                links = await page_links(page)
                count = 0
                for link in links:
                    asset = file_asset(link, module['label'], module['id'])
                    if asset:
                        found[source_key(asset['url'])] = asset
                        count += 1
                if module['kind'] == 'page':
                    content = await page.evaluate('''() => {
                        const original=document.querySelector('#region-main') || document.querySelector('main') || document.body;
                        const root=original.cloneNode(true);
                        root.querySelectorAll('script,style,form,input,iframe,object,embed').forEach(el=>el.remove());
                        root.querySelectorAll('*').forEach(el=>[...el.attributes].forEach(a=>{if(a.name.startsWith('on'))el.removeAttribute(a.name)}));
                        root.querySelectorAll('a[href]').forEach(a=>{if(a.href.startsWith('javascript:'))a.removeAttribute('href');else a.href=a.href});
                        return root.innerHTML;
                    }''')
                    name = safe_name(module['label']) + '.html'
                    body = '<!DOCTYPE html><html><meta charset="utf-8"><title>%s</title><body>%s</body></html>' % (html.escape(module['label']), content)
                    found[source_key(module['url'])] = {'kind': 'page', 'url': module['url'], 'name': name, 'group': module['label'],
                                                       'module_id': module['id'], 'relative': name, 'body': body}
                elif not count:
                    issues.append(module['label'] + ': nessun file leggibile; HTML salvato per verifica')
            except Exception as exc:
                issues.append(module['label'] + ': ' + (str(exc) if isinstance(exc, DownloadError) else 'pagina non leggibile'))
            finally:
                await save_listing(page)
        for issue in issues:
            print('  Da verificare: ' + issue)
        if not found:
            raise DownloadError('Non ho trovato file scaricabili. Gli HTML delle cartelle visitate sono disponibili per la verifica.')
        return sorted(found.values(), key=lambda a: (a['group'].casefold(), a['name'].casefold()))
    finally:
        await save_listing(page)
        await page.close()


async def choose_materials(assets):
    print('\n%d materiali trovati.' % len(assets))
    while True:
        print('1) Tutti i materiali trovati\n2) Scegli singoli file o pagine\n3) Scegli cartelle/gruppi\nq) Torna indietro')
        value = (await ask('Scelta [1] > ')).strip().lower() or '1'
        if value == 'q':
            return []
        if value == '1':
            return assets
        try:
            if value == '2':
                for i, asset in enumerate(assets, 1):
                    print('%d) %s / %s' % (i, asset['group'], asset['name']))
                indices = selection_numbers(await ask('Numeri o intervalli (es. 1,3,5-8) > '), len(assets))
                return [assets[i] for i in indices]
            if value == '3':
                groups = sorted({a['group'] for a in assets})
                for i, group in enumerate(groups, 1):
                    print('%d) %s (%d elementi)' % (i, group, sum(a['group'] == group for a in assets)))
                indices = selection_numbers(await ask('Cartelle/gruppi da scaricare > '), len(groups))
                selected = {groups[i] for i in indices}
                return [a for a in assets if a['group'] in selected]
        except ValueError as exc:
            print(str(exc))


def save_material(client, asset, base, index):
    key = source_key(asset['url'])
    previous = index.get(key, {})
    old = base / previous.get('path', '__missing__')
    valid = base.resolve() in old.resolve().parents and old.is_file() and hashlib.sha256(old.read_bytes()).hexdigest() == previous.get('sha256')
    headers = {}
    if valid:
        if previous.get('etag'):
            headers['If-None-Match'] = previous['etag']
        elif previous.get('modified'):
            headers['If-Modified-Since'] = previous['modified']
        elif asset['kind'] != 'page':
            return 'present'
    if asset['kind'] == 'page':
        payload = asset['body'].encode('utf-8')
        name, etag, modified = asset['name'], None, None
        if valid and hashlib.sha256(payload).hexdigest() == previous.get('sha256'):
            return 'present'
        response = None
    else:
        response = client.stream('GET', asset['url'], headers=headers)
    def destination(name):
        relative = asset.get('relative') or name
        parts = [safe_name(p) for p in relative.replace('\\', '/').split('/') if p not in ('', '.', '..')]
        group = slug(asset['group']) + '_' + asset['module_id']
        return base / group / Path(*parts)
    def commit(target, digest, length, etag, modified):
        index[key] = {'path': str(target.relative_to(base)), 'sha256': digest, 'bytes': length,
                      'etag': etag, 'modified': modified, 'source': key, 'title': asset['name']}
    if response is None:
        target = destination(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + '.part')
        partial.write_bytes(payload)
        partial.replace(target)
        commit(target, hashlib.sha256(payload).hexdigest(), len(payload), etag, modified)
        return 'downloaded'
    with response as result:
        if result.status_code == 304 and valid:
            return 'present'
        if result.status_code != 200:
            raise DownloadError('Download materiale HTTP %d.' % result.status_code)
        parsed = urlsplit(str(result.url))
        if parsed.hostname != 'webeep.polimi.it' or '/login/' in parsed.path:
            raise DownloadError('Il materiale richiede un nuovo accesso a WeBeep.')
        ctype = result.headers.get('content-type', '').split(';')[0].lower()
        if ctype == 'text/html' and ('/pluginfile.php/' not in parsed.path or not parsed.path.lower().endswith(('.html', '.htm'))):
            raise DownloadError('Il modulo ha restituito una pagina, non un file; aprilo nel browser per salvare l’HTML e verificarlo.')
        message = Message()
        message['Content-Disposition'] = result.headers.get('content-disposition', '')
        name = message.get_filename() or unquote(parsed.path.rsplit('/', 1)[-1])
        if name in ('view.php', ''):
            name = asset['name'] + (mimetypes.guess_extension(ctype) or '.bin')
        name = safe_name(name.replace('\\', '/').rsplit('/', 1)[-1])
        target = destination(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + '.part')
        digest, written = hashlib.sha256(), 0
        with partial.open('wb') as stream:
            for chunk in result.iter_bytes():
                stream.write(chunk)
                digest.update(chunk)
                written += len(chunk)
        length = result.headers.get('content-length')
        if written == 0 or (length and not result.headers.get('content-encoding') and written != int(length)):
            raise DownloadError('Materiale incompleto: non segnato come scaricato.')
        partial.replace(target)
        commit(target, digest.hexdigest(), written, result.headers.get('etag'), result.headers.get('last-modified'))
        return 'downloaded'


async def download_materials(context, catalog, course):
    from .cli import make_client
    import httpx
    assets = await discover_materials(context, course)
    selected = await choose_materials(assets)
    if not selected:
        return
    base = catalog.root / 'corsi' / slug(course['label']) / 'materiali'
    base.mkdir(parents=True, exist_ok=True)
    index_path = base / 'index.json'
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    page = next((p for p in context.pages if not p.is_closed()), None)
    agent = await page.evaluate('navigator.userAgent') if page else 'PolimiLectures'
    cookies = await context.cookies()
    downloaded = present = failed = 0
    with make_client(cookies, agent, course['url']) as client:
        for i, asset in enumerate(selected, 1):
            print('[%d/%d] %s / %s' % (i, len(selected), asset['group'], asset['name']), flush=True)
            try:
                outcome = save_material(client, asset, base, index)
                downloaded += outcome == 'downloaded'
                present += outcome == 'present'
                temp = index_path.with_suffix('.json.tmp')
                temp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
                temp.replace(index_path)
            except (DownloadError, httpx.HTTPError, OSError) as exc:
                failed += 1
                print('  Non riuscito: ' + (str(exc) if isinstance(exc, DownloadError) else type(exc).__name__))
    print('\nMateriali: %d scaricati, %d già presenti, %d non riusciti.\nCartella: %s' % (downloaded, present, failed, base))
