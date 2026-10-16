import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from playwright.async_api import async_playwright

from polimi_lectures.core import Catalog, DownloadError
from polimi_lectures.guided import COURSES, all_recordings, course_matches, guided, in_range, parse_date

RID1 = '11111111111111111111111111111111'
RID2 = '22222222222222222222222222222222'
WEBEX = 'https://politecnicomilano.webex.com/recordingservice/sites/politecnicomilano/recording/playback/'
RECMAN = 'https://onlineservices.polimi.it/recman_frontend/recman_frontend/controller/UserListActivity.do'
LABEL = '058165 - PARALLEL COMPUTING (FERRANDI FABRIZIO) [2025-26]'


class SelectionTests(unittest.TestCase):
    def test_course_name_tolerates_typo_but_not_unrelated_subject(self):
        self.assertTrue(course_matches('paralel computing', LABEL))
        self.assertTrue(course_matches('058165', LABEL))
        self.assertFalse(course_matches('software engineering', LABEL))

    def test_dates_are_inclusive_and_unknown_dates_excluded(self):
        records = [{'date': '2025-09-16'}, {'date': '2025-10-01'}, {'date': '2025-11-04'}, {'date': None}]
        self.assertEqual(in_range(records, '2025-10-01', '2025-11-04'), records[1:3])
        self.assertEqual(parse_date('01/10/2025'), '2025-10-01')
        with self.assertRaises(ValueError):
            parse_date('31/02/2025')


class GuidedBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.catalog = Catalog(self.temp.name)
        self.pw = await async_playwright().start()
        if not Path(self.pw.chromium.executable_path).exists():
            await self.pw.stop()
            self.catalog.db.close()
            self.temp.cleanup()
            self.skipTest('Chromium non installato')
        self.browser = await self.pw.chromium.launch(headless=True)
        self.context = await self.browser.new_context()
        self.opened = []
        self.mode = None
        self.preferences = patch('polimi_lectures.config.remember_course')
        self.preferences.start()
        self.preference_read = patch('polimi_lectures.config.load_config', return_value={})
        self.preference_read.start()
        await self.context.route('**/*', self.respond)

    async def asyncTearDown(self):
        await self.context.close()
        await self.browser.close()
        await self.pw.stop()
        self.preferences.stop()
        self.preference_read.stop()
        self.catalog.db.close()
        self.temp.cleanup()

    def rows(self, which='both'):
        rows = []
        if which in ('both', 'later'):
            rows.append('<tr><td>04/11/2025 08:30</td><td>CUDA</td><td><a title="Riproduci" target="_blank" href="%s?lesson=2"></a></td></tr>' % RECMAN)
        if which in ('both', 'first'):
            rows.append('<tr><td>16/09/2025 08:30</td><td>PRAM</td><td><a title="Riproduci" target="_blank" href="%s?lesson=1"></a></td></tr>' % RECMAN)
        return '<table>' + ''.join(rows) + '</table>'

    async def respond(self, route):
        url = route.request.url
        if url.startswith(RECMAN) and self.mode == 'slow':
            if 'all=1' in url:
                import json
                body = '<p>pag. 1/1 (totale:2)</p><div id="rows"></div><script>setTimeout(() => document.querySelector("#rows").innerHTML=%s, 350)</script>' % json.dumps(self.rows())
                # Anche se RecMan conserva per errore un link prossima, siamo già all'ultima pagina.
                body += '<a class="paginator_link" href="%s?page=2">prossima</a>' % RECMAN
            else:
                body = '<p>pag. 1/2 (totale:2)</p>' + self.rows('later')
                body += '<a class="paginator_link" href="%s?all=1">tutte</a>' % RECMAN
                body += '<script>document.addEventListener("click", e => {if(e.target.matches("a.paginator_link")){e.preventDefault();setTimeout(()=>location.href=e.target.href,500)}})</script>'
            await route.fulfill(content_type='text/html', body=body)
            return
        if url.startswith(RECMAN) and self.mode == 'duplicate':
            body = '<p>pag. 1/2 (totale:2)</p>' + self.rows('later')
            body += '<a class="paginator_link" href="%s?page=2">prossima</a>' % RECMAN
            await route.fulfill(content_type='text/html', body=body)
            return
        if url.startswith(RECMAN) and self.mode == 'missing':
            body = '<p>pag. 1/1 (totale:3)</p>' + self.rows()
            await route.fulfill(content_type='text/html', body=body)
            return
        if url == COURSES:
            body = '<a href="https://webeep.polimi.it/auth/shibboleth/index.php">Polimi login</a>'
        elif '/auth/shibboleth/' in url:
            body = '<a href="https://webeep.polimi.it/course/view.php?id=19784">%s</a><a href="https://webeep.polimi.it/course/view.php?id=23947">058165 - PARALLEL COMPUTING [2026-27]</a>' % LABEL
        elif '/course/view.php' in url:
            body = '<a href="https://webeep.polimi.it/course/section.php?id=95035">Registrazioni</a>'
        elif '/course/section.php' in url:
            body = '<a href="https://webeep.polimi.it/mod/url/view.php?id=368676">Archivio registrazioni</a>'
        elif '/mod/url/view.php' in url:
            target = 'https://aunicalogin.polimi.it/handoff' if self.mode == 'sso' else RECMAN
            body = '<meta http-equiv="refresh" content="0;url=%s">' % target
        elif url.startswith('https://aunicalogin.polimi.it/handoff'):
            body = '<meta http-equiv="refresh" content="0.2;url=%s">' % RECMAN
        elif url.startswith(RECMAN) and 'lesson=' in url:
            rid = RID1 if 'lesson=1' in url else RID2
            self.opened.append(rid)
            body = '<meta http-equiv="refresh" content="0;url=%s">' % (WEBEX + rid)
        elif url.startswith(WEBEX):
            body = '<title>Webex player</title>'
        elif url.startswith(RECMAN) and 'all=1' in url:
            body = self.rows()
        elif url.startswith(RECMAN) and 'page=2' in url:
            body = self.rows('first')
        elif url.startswith(RECMAN) and 'paginate=1' in url:
            body = self.rows('later') + '<a class="paginator_link" href="%s?page=2">prossima</a>' % RECMAN
        elif url.startswith(RECMAN):
            body = self.rows('later') + '<a class="paginator_link" href="%s?all=1">tutte</a>' % RECMAN
        else:
            await route.abort()
            return
        await route.fulfill(content_type='text/html', body=body)

    async def test_login_course_year_section_all_pages_and_single_test_recording(self):
        with patch('polimi_lectures.guided.ask', new=AsyncMock(side_effect=['1', '1'])):
            rows = await guided(self.context, self.catalog, 'paralel computing')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], RID1)
        self.assertEqual(rows[0]['date'], '2025-09-16')
        self.assertEqual(rows[0]['course'], LABEL)
        self.assertEqual(self.opened, [RID1])

    async def test_date_range_does_not_open_excluded_recordings(self):
        with patch('polimi_lectures.guided.ask', new=AsyncMock(side_effect=['1', '2', '01/11/2025', '04/11/2025'])):
            rows = await guided(self.context, self.catalog, 'Parallel Computing')
        self.assertEqual([row['id'] for row in rows], [RID2])
        self.assertEqual(self.opened, [RID2])

    async def test_next_page_fallback_collects_entire_list(self):
        page = await self.context.new_page()
        await page.goto(RECMAN + '?paginate=1')
        rows = await all_recordings(page)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['date'], '2025-09-16')

    async def test_delayed_rows_and_async_click_handler_do_not_repeat_page(self):
        self.mode = 'slow'
        page = await self.context.new_page()
        await page.goto(RECMAN)
        records = await all_recordings(page)
        self.assertEqual(len(records), 2)
        self.assertIn('all=1', page.url)

    async def test_real_repeated_page_still_reports_incomplete_collection(self):
        self.mode = 'duplicate'
        page = await self.context.new_page()
        await page.goto(RECMAN)
        with self.assertRaisesRegex(DownloadError, 'stesse lezioni'):
            await all_recordings(page)

    async def test_server_total_must_match_collected_recordings(self):
        self.mode = 'missing'
        page = await self.context.new_page()
        await page.goto(RECMAN)
        with self.assertRaisesRegex(DownloadError, '2 registrazioni su 3'):
            await all_recordings(page)

    async def test_sso_handoff_finishes_without_extra_terminal_confirmation(self):
        self.mode = 'sso'
        answers = AsyncMock(side_effect=['1', '1'])
        with patch('polimi_lectures.guided.ask', new=answers):
            rows = await guided(self.context, self.catalog, 'Parallel Computing')
        self.assertEqual(len(rows), 1)
        self.assertEqual(answers.await_count, 2)

    async def test_short_course_name_reuses_saved_year_without_prompt(self):
        from polimi_lectures.guided import choose_course
        links = [{'url': 'https://webeep.polimi.it/course/view.php?id=19784', 'label': LABEL},
                 {'url': 'https://webeep.polimi.it/course/view.php?id=23947', 'label': 'PARALLEL COMPUTING [2026-27]'}]
        with patch('polimi_lectures.config.load_config', return_value={'last_course': LABEL}), \
             patch('polimi_lectures.guided.ask', new=AsyncMock(side_effect=AssertionError('Non deve richiedere l’anno'))):
            selected = await choose_course(links, 'parallel computing')
        self.assertEqual(selected['label'], LABEL)
        self.assertFalse(course_matches('parallel computing 2026-27', LABEL))

    async def test_continue_uses_same_course_and_recordings_without_reselecting(self):
        state = {}
        with patch('polimi_lectures.guided.ask', new=AsyncMock(side_effect=['1', '1', '1'])):
            first = await guided(self.context, self.catalog, 'Parallel Computing', state)
            second = await guided(self.context, self.catalog, 'Parallel Computing', state)
        self.assertEqual(first[0]['id'], second[0]['id'])
        self.assertEqual(self.opened, [RID1, RID1])
