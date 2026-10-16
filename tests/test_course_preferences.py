import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from polimi_lectures.config import load_config, remember_course
from polimi_lectures.guided import choose_course


def link(name, year, number):
    return {'label': '012345 - %s (DOCENTE) [%s]' % (name, year),
            'url': 'https://webeep.polimi.it/course/view.php?id=%s' % number}


class CoursePreferencesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = patch('polimi_lectures.config.project_root', return_value=Path(self.temp.name))
        self.root.start()
        self.addCleanup(self.root.stop)
        self.addCleanup(self.temp.cleanup)
        self.a = [link('SOFTWARE ENGINEERING', '2025-26', 1),
                  link('SOFTWARE ENGINEERING', '2026-27', 2)]
        self.b = [link('COMPUTER NETWORKS', '2025-26', 3),
                  link('COMPUTER NETWORKS', '2026-27', 4)]
        self.links = self.a + self.b

    async def select(self, query):
        selected = await choose_course(self.links, query)
        remember_course(selected['label'], selected['url'], query)
        return selected

    async def test_first_visit_asks_and_each_subject_keeps_its_own_year(self):
        with patch('polimi_lectures.guided.ask', new=AsyncMock(side_effect=['1', '2'])) as ask:
            self.assertEqual(await self.select('software engineering'), self.a[0])
            self.assertEqual(await self.select('computer networks'), self.b[1])
            self.assertEqual(ask.await_count, 2)
        with patch('polimi_lectures.guided.ask', new=AsyncMock(side_effect=AssertionError('Unexpected prompt'))):
            self.assertEqual(await self.select('  Software   Engineering '), self.a[0])
            self.assertEqual(await self.select('Computer Networks'), self.b[1])

    async def test_explicit_year_changes_only_that_subject_preference(self):
        remember_course(self.a[0]['label'], self.a[0]['url'], 'software engineering')
        remember_course(self.b[1]['label'], self.b[1]['url'], 'computer networks')
        with patch('polimi_lectures.guided.ask', new=AsyncMock(side_effect=AssertionError('Unexpected prompt'))):
            self.assertEqual(await self.select('software engineering 2026-27'), self.a[1])
            self.assertEqual(await self.select('software engineering'), self.a[1])
            self.assertEqual(await self.select('computer networks'), self.b[1])

    async def test_unknown_subject_still_asks_even_with_last_course(self):
        remember_course(self.a[0]['label'], self.a[0]['url'], 'software engineering')
        with patch('polimi_lectures.guided.ask', new=AsyncMock(return_value='2')) as ask:
            self.assertEqual(await self.select('computer networks'), self.b[1])
            ask.assert_awaited_once()

    async def test_legacy_full_label_choices_remain_available_after_other_courses(self):
        config = {'last_course': self.b[1]['label'], 'course_choices': {
            self.a[0]['label'].lower(): self.a[0], self.b[1]['label'].lower(): self.b[1]}}
        with patch('polimi_lectures.config.load_config', return_value=config), patch(
                'polimi_lectures.guided.ask', new=AsyncMock(side_effect=AssertionError('Unexpected prompt'))):
            self.assertEqual(await choose_course(self.links, 'software engineering'), self.a[0])

    async def test_unavailable_saved_year_requests_selection(self):
        remember_course(self.a[0]['label'], self.a[0]['url'], 'software engineering')
        links = [link('SOFTWARE ENGINEERING', '2027-28', 5), self.a[1]]
        with patch('polimi_lectures.guided.ask', new=AsyncMock(return_value='2')) as ask:
            self.assertEqual(await choose_course(links, 'software engineering'), self.a[1])
            ask.assert_awaited_once()

    async def test_saving_keeps_other_settings(self):
        state = Path(self.temp.name) / '.state'
        state.mkdir()
        (state / 'settings.json').write_text('{"email":"student@example.org","data_dir":"/some/disk"}')
        remember_course(self.a[0]['label'], self.a[0]['url'], 'software engineering')
        self.assertEqual(load_config()['email'], 'student@example.org')
        self.assertEqual(load_config()['data_dir'], '/some/disk')
