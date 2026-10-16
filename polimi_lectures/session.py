"""Assistenza al login email e diagnostica HTML privata, senza password o cookie esportati."""
import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from .ui import detail


async def fill_webex_email(page, email):
    host = (urlsplit(page.url).hostname or "").lower()
    if not email or not (host == "webex.com" or host.endswith(".webex.com")):
        return False
    try:
        if await page.locator('input[type="password"]:visible').count():
            return False
        if await page.evaluate("Boolean(window.__polimiEmailSubmitted)"):
            return False
        fields = [
            page.get_by_label(re.compile(r"^(indirizzo\s+e[- ]?mail|e[- ]?mail(?:\s+address)?)\s*[:*]?$", re.I)),
            page.locator('input[type="email"]:visible, input[name="email"]:visible, input[name="emailAddress"]:visible, input#email:visible, input#IDToken1:visible'),
        ]
        field = None
        for locator in fields:
            if await locator.count() and await locator.first.is_visible():
                field = locator.first
                break
        if field is None:
            return False
        buttons = [page.locator('button#IDButton2:visible, input#IDButton2:visible'),
                   page.get_by_role("button", name=re.compile(r"^(accedi|sign in|log in|next|avanti|continua|continue)$", re.I)),
                   page.get_by_role("link", name=re.compile(r"^(accedi|sign in|log in|next|avanti|continua|continue)$", re.I))]
        button = None
        for candidate in buttons:
            if await candidate.count() and await candidate.first.is_visible():
                button = candidate.first
                break
        if button is None:
            return False
        # Invoca gli eventi del form senza spostare il focus del desktop.
        if await field.input_value() != email:
            await field.evaluate('''(el, value) => {
                Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, value);
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
            }''', email)
        else:
            await field.dispatch_event('input')
        if not await button.is_enabled():
            return False
        await page.evaluate("window.__polimiEmailSubmitted = true")
        try:
            await button.click(timeout=3000, no_wait_after=True)
        except Exception:
            try:
                await page.evaluate('window.__polimiEmailSubmitted = false')
            except Exception:
                pass
            return False
        detail("  Email Polimi inserita e inviata a Webex.")
        return True
    except Exception:
        return False


async def start_webex_playback(page):
    parsed = urlsplit(page.url)
    if not (parsed.hostname or '').endswith('.webex.com') or 'recording' not in parsed.path:
        return False
    try:
        if await page.evaluate('Boolean(window.__polimiPlaybackStarted)'):
            return False
        # Quando consentito, play() non richiede clic né cambio di focus.
        played = await page.evaluate('''async () => {
            const video = document.querySelector('video');
            if (!video) return false;
            if (!video.paused) return true;
            try {
                return await Promise.race([video.play().then(() => true),
                    new Promise(resolve => setTimeout(() => resolve(false), 1500))]);
            } catch { return false; }
        }''')
        if played:
            await page.evaluate('window.__polimiPlaybackStarted = true')
            return True
        button = page.get_by_role('button', name=re.compile(r'^(play|riproduci|avvia)(\s+(video|recording|registrazione))?$', re.I)).first
        if await button.count() and await button.is_visible() and await button.is_enabled():
            await button.click(timeout=2000, no_wait_after=True)
            await page.evaluate('window.__polimiPlaybackStarted = true')
            return True
    except Exception:
        pass
    return False


class BrowserAssistant:
    def __init__(self, context, root, email=None, debug_html=False, auth_path=None):
        self.context = context
        self.email = email
        self.debug_html = debug_html
        self.tasks = set()
        self.pages = set()
        self.handlers = {}
        self.hashes = {}
        self.counter = 0
        self.auth_path = auth_path
        self.auth_last_save = 0
        self.auth_lock = asyncio.Lock()
        self.directory = root / ".state" / "debug-html" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        if debug_html:
            self.directory.mkdir(parents=True, mode=0o700)
            self.directory.chmod(0o700)
            detail("HTML diagnostici locali: %s" % self.directory)

    def start(self):
        self.context.on("page", self.watch)
        for page in self.context.pages:
            self.watch(page)

    def watch(self, page):
        if page in self.pages:
            return
        self.pages.add(page)
        def capture(*args):
            task = asyncio.create_task(self.save_page(page))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        self.handlers[page] = capture
        page.on("domcontentloaded", capture)
        page.on("framenavigated", capture)
        task = asyncio.create_task(self.run_page(page))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def run_page(self, page):
        while not page.is_closed():
            await self.save_access()
            await self.save_page(page)
            submitted = await fill_webex_email(page, self.email)
            if submitted:
                await self.save_page(page)
            await asyncio.sleep(1.5)

    async def save_access(self, force=False):
        if self.auth_path is None:
            return
        async with self.auth_lock:
            if not force and time.monotonic() - self.auth_last_save < 10:
                return
            self.auth_last_save = time.monotonic()
            try:
                from .auth import save_auth
                await save_auth(self.context, self.auth_path)
            except Exception:
                print('Non riesco a salvare lo stato di accesso locale: controlla spazio e permessi.', flush=True)

    async def save_page(self, page):
        if not self.debug_html or page.is_closed():
            return
        for index, frame in enumerate(page.frames):
            try:
                if not frame.url or frame.url == "about:blank":
                    continue
                # Clona il DOM senza toccare la pagina reale. Non esporta i valori
                # dei campi password/hidden (token di form e credenziali).
                content = await frame.evaluate("""() => {
                    if (!document.documentElement) return '';
                    const root = document.documentElement.cloneNode(true);
                    root.querySelectorAll('input[type=password],input[type=hidden]').forEach(el => {
                        el.removeAttribute('value');
                    });
                    return '<!DOCTYPE html>\\n' + root.outerHTML;
                }""")
                if not content:
                    continue
                key = (page, frame)
                digest = hashlib.sha256((frame.url + content).encode()).hexdigest()
                if self.hashes.get(key) == digest:
                    continue
                self.hashes[key] = digest
                self.counter += 1
                parsed = urlsplit(frame.url)
                host = re.sub(r"[^a-zA-Z0-9.-]", "_", parsed.hostname or "pagina")
                name = "%05d_%s_frame%d" % (self.counter, host, index)
                path = self.directory / (name + ".html")
                path.write_text(content, encoding="utf-8")
                path.chmod(0o600)
                metadata = {"captured_at": datetime.now(timezone.utc).isoformat(),
                            "url_without_query": urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")),
                            "frame_index": index}
                info = self.directory / (name + ".json")
                info.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                info.chmod(0o600)
            except OSError:
                print("  Salvataggio HTML non riuscito: controlla spazio disco e permessi.", flush=True)
                self.debug_html = False
                return
            except Exception:
                # Redirect e chiusure possono distruggere il frame mentre lo leggiamo.
                continue

    async def stop(self):
        self.context.remove_listener("page", self.watch)
        for page, handler in self.handlers.items():
            page.remove_listener("domcontentloaded", handler)
            page.remove_listener("framenavigated", handler)
        for task in list(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
        for page in list(self.context.pages):
            await self.save_page(page)
        await self.save_access(force=True)


def settings(root):
    from .config import load_config
    return load_config()
