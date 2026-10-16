import asyncio
import html
import json
import re
from urllib.parse import urlsplit

from .core import DownloadError, media_candidates, webex_id
from .ui import detail

ARCHIVE = "https://onlineservices.polimi.it/recman_frontend/recman_frontend/controller/UserListActivity.do"


async def ask(message):
    return await asyncio.to_thread(input, message)


async def launch(playwright, root, channel=None):
    from .config import project_root
    profile = project_root() / ".state" / "browser"
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    profile.chmod(0o700)
    kwargs = {"headless": False, "accept_downloads": False}
    if channel:
        kwargs["channel"] = channel
    context = await playwright.chromium.launch_persistent_context(str(profile), **kwargs)
    from .auth import restore_auth
    auth_path = project_root() / '.state' / 'auth-state.json'
    if await restore_auth(context, auth_path):
        detail('Stato di accesso locale ripristinato. Verifico la sessione sul portale…')
    from .session import BrowserAssistant, settings
    config = settings(root)
    assistant = BrowserAssistant(context, root, config.get("email"), config.get("debug_html", False), auth_path=auth_path)
    context._polimi_assistant = assistant
    assistant.start()
    return context


def date_from_text(text):
    match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if match:
        value = match[0]
    else:
        match = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](20\d{2})\b", text)
        if not match:
            return None
        value = "%s-%02d-%02d" % (match[3], int(match[2]), int(match[1]))
    from datetime import date
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


async def scan(context, catalog, course):
    added = 0
    for page in list(context.pages):
        if page.is_closed():
            continue
        if webex_id(page.url):
            added += catalog.add(course, page.url, await page.title())
        for frame in page.frames:
            try:
                links = await frame.locator("a, [onclick]").evaluate_all("""els => els.map(el => ({
                    href: el.href || '', onclick: el.getAttribute('onclick') || '',
                    title: el.innerText || el.title || el.getAttribute('aria-label') || '',
                    row: (el.closest('tr') || el).innerText || ''
                }))""")
            except Exception:
                continue
            for link in links:
                urls = [link["href"]]
                text = html.unescape(link["onclick"]).replace("\\/", "/")
                urls.extend(re.findall(r'https://[^\s\'"<>]+', text))
                for url in urls:
                    if webex_id(url):
                        title = " ".join(link["row"].split()) or link["title"]
                        added += catalog.add(course, url, title, date_from_text(link["row"]))
    return added


async def auto_controls(context, page, catalog, course, selector=None):
    """Navigazione seriale; niente tentativi di ricostruire form/token RecMan."""
    controls = page.locator(selector or 'a, button, input[type="button"], input[type="submit"], input[type="image"]')
    entries = await controls.evaluate_all("""els => els.map(el => ({
        label: [el.innerText, el.value, el.title, el.getAttribute('aria-label'), el.alt].filter(Boolean).join(' '),
        row: (el.closest('tr') || el).innerText || ''
    }))""")
    labels = [entry['label'] for entry in entries]
    indices = list(range(len(labels))) if selector else [
        i for i, label in enumerate(labels)
        if re.search(r"riproduci|\bplay\b|guarda|visualizza\s+(?:la\s+)?registrazione", label, re.I)
        and not re.search(r"elimina|cancella|delete", label, re.I)
    ]
    if not indices:
        print("Nessun pulsante di riproduzione riconosciuto. Apri una lezione manualmente e usa s.")
        return 0
    print("Pulsanti di riproduzione da aprire: %d" % len(indices))
    added = 0
    for n, index in enumerate(indices, 1):
        if page.is_closed():
            break
        before_pages = set(context.pages)
        before_url = page.url
        navigations = []

        def remember(frame):
            if frame == page.main_frame:
                navigations.append(frame.url)

        page.on("framenavigated", remember)
        try:
            await controls.nth(index).click(timeout=8000)
            # Lascia che redirect, popup e pagine SPA si assestino.
            for _ in range(24):
                await page.wait_for_timeout(500)
                candidates = [p for p in context.pages if p not in before_pages]
                if webex_id(page.url) or any(webex_id(p.url) for p in candidates):
                    break
            added += await scan(context, catalog, course)
            recording_urls = navigations + [p.url for p in context.pages if p not in before_pages]
            for url in recording_urls:
                if webex_id(url):
                    entry = entries[index]
                    added += catalog.add(course, url, ' '.join(entry['row'].split()) or labels[index], date_from_text(entry['row']))
            print("  Lezione %d/%d esaminata" % (n, len(indices)))
        except Exception:
            print("  Pulsante %d non risolto: usa la navigazione manuale." % n)
        finally:
            page.remove_listener("framenavigated", remember)
            for popup in list(context.pages):
                if popup not in before_pages:
                    await popup.close()
            if navigations or page.url != before_url:
                try:
                    await page.go_back(wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    print("Ritorno all'elenco non riuscito: interrompo la scansione automatica.")
                    break
    return added


async def discover(context, catalog, course, url=None, selector=None):
    page = context.pages[0] if context.pages else await context.new_page()
    try:
        await page.goto(url or ARCHIVE, wait_until="domcontentloaded", timeout=45000)
    except Exception:
        print("Completa l'accesso e raggiungi l'elenco registrazioni nel browser.")
    print("\nAccedi, scegli SOLO il corso richiesto e apri l'elenco registrazioni.")
    print("s = raccogli link da tutte le schede; a = apri automaticamente i pulsanti di riproduzione")
    print("Puoi cambiare pagina manualmente e ripetere s/a. q = termina e salva.\n")
    while True:
        command = (await ask("[s/a/q] > ")).strip().lower() or "s"
        if command == "q":
            break
        if command == "s":
            added = await scan(context, catalog, course)
        elif command == "a":
            # L'elenco può essere in una nuova scheda: sceglie l'ultima pagina non-Webex.
            listings = [p for p in context.pages if not p.is_closed() and not webex_id(p.url)]
            if not listings:
                print("Apri prima la scheda con l'elenco del corso.")
                continue
            added = await auto_controls(context, listings[-1], catalog, course, selector)
        else:
            continue
        print("Nuove registrazioni: %d. Totale corso: %d." % (added, len(catalog.rows(course))))


async def resolve(context, row, timeout=40):
    page = await context.new_page()
    candidates = []
    pending = set()
    titles = []

    async def inspect(response):
        try:
            parsed = urlsplit(response.url)
            if response.status not in (200, 206):
                return
            if ".m3u8" in parsed.path.lower():
                candidates.append(("hls", response.url))
            elif parsed.path.lower().endswith(".mp4") and response.request.resource_type == "media":
                candidates.append(("mp4", response.url))
            elif "recordings/" in parsed.path and "/stream" in parsed.path:
                data = await response.json()
                candidates.extend(media_candidates(data))
                if isinstance(data, dict) and data.get("recordName"):
                    titles.append(str(data["recordName"]))
        except Exception:
            pass

    def observe(response):
        task = asyncio.create_task(inspect(response))
        pending.add(task)
        task.add_done_callback(pending.discard)

    page.on("response", observe)
    try:
        try:
            await page.goto(row["url"], wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass
        detail("  Apro Webex: riutilizzo la sessione e completo automaticamente email e avvio del player.")
        for _ in range(timeout * 2):
            await page.wait_for_timeout(500)
            if candidates:
                await page.wait_for_timeout(1500)
                break
            from .session import start_webex_playback
            await start_webex_playback(page)
        if not candidates:
            await ask("  Il player non ha ancora fornito il video. Controlla eventuali richieste di password/SPID o errori nel browser, poi Invio > ")
            await page.wait_for_timeout(3000)
        if pending:
            await asyncio.gather(*list(pending), return_exceptions=True)
        if not candidates:
            raise DownloadError("Nessun URL video rilevato: accesso, player o formato da verificare.")
        cookies = await context.cookies()
        agent = await page.evaluate("navigator.userAgent")
        return list(dict.fromkeys(candidates)), cookies, agent, page.url, (titles[-1] if titles else None)
    finally:
        assistant = getattr(context, "_polimi_assistant", None)
        if assistant:
            await assistant.save_page(page)
        page.remove_listener("response", observe)
        for task in list(pending):
            task.cancel()
        if pending:
            await asyncio.gather(*list(pending), return_exceptions=True)
        await page.close()
