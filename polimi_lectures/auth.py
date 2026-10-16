"""Salvataggio privato dell'accesso Polimi/Webex, senza prolungare la scadenza dei cookie."""
import json
import time
from urllib.parse import urlsplit


def relevant_host(host):
    host = host.lower().lstrip('.')
    return host in ('polimi.it', 'webex.com') or host.endswith(('.polimi.it', '.webex.com'))


async def save_auth(context, path):
    # storage_state() può creare una scheda temporanea per gli origin non più
    # aperti, portando Chrome in primo piano. Leggi solo cookie e frame esistenti.
    origins = {}
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding='utf-8'))
            origins = {origin['origin']: origin for origin in previous.get('origins', [])
                       if relevant_host(urlsplit(origin.get('origin', '')).hostname or '')}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    for page in list(context.pages):
        if page.is_closed():
            continue
        for frame in list(page.frames):
            if not relevant_host(urlsplit(frame.url).hostname or ''):
                continue
            try:
                storage = await frame.evaluate('''() => ({origin: location.origin,
                    localStorage: Object.keys(localStorage).map(name => ({name, value: localStorage.getItem(name)}))
                })''')
                if relevant_host(urlsplit(storage['origin']).hostname or ''):
                    origins[storage['origin']] = storage
            except Exception:
                continue
    data = {
        'cookies': [cookie for cookie in await context.cookies() if relevant_host(cookie.get('domain', ''))],
        'origins': list(origins.values()),
    }
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(path)


async def restore_auth(context, path):
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        current = {(cookie['name'], cookie['domain'], cookie['path']) for cookie in await context.cookies()}
        cookies = []
        for cookie in data.get('cookies', []):
            if not relevant_host(cookie.get('domain', '')):
                continue
            if cookie.get('expires', -1) != -1 and cookie['expires'] <= time.time():
                continue
            if (cookie['name'], cookie['domain'], cookie['path']) not in current:
                cookies.append(cookie)
        if cookies:
            await context.add_cookies(cookies)
        origins = {origin['origin']: origin.get('localStorage', []) for origin in data.get('origins', [])
                   if relevant_host(urlsplit(origin.get('origin', '')).hostname or '')}
        if origins:
            await context.add_init_script('''(() => {
                const values = %s[location.origin] || [];
                for (const item of values) {
                    if (localStorage.getItem(item.name) === null) localStorage.setItem(item.name, item.value);
                }
            })();''' % json.dumps(origins))
        return bool(cookies or origins)
    except Exception:
        print('Stato di accesso locale non leggibile: verifico la sessione presente nel browser.', flush=True)
        return False
