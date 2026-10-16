import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from polimi_lectures.cli import progress_reporter
from polimi_lectures.core import Catalog, DownloadError
from polimi_lectures.progress import BatchProgress, recording_bytes
from polimi_lectures.workflow import download_rows


def row(ident, title, size=None):
    return {'course': 'Any course', 'id': ident, 'title': title, 'size_bytes': size, 'date': None}


class ProgressTests(unittest.TestCase):
    def test_sizes_from_recording_listing(self):
        self.assertEqual(recording_bytes('Lecture 41 min 117,5 MB'), 117500000)
        self.assertEqual(recording_bytes('Lecture 1.2 GB'), 1200000000)
        self.assertIsNone(recording_bytes('Lecture without a size'))

    def test_resume_counts_available_bytes_once_and_refreshes_estimates(self):
        a, b = row('a', 'A', 100000000), row('b', 'B', 200000000)
        batch = BatchProgress([a, b])
        batch.start(a)
        batch.report(40000000, 120000000)
        self.assertIn('12%', batch.text())
        self.assertIn('40.0 / ≈ 320.0 MB', batch.text())
        batch.report(60000000, 120000000)
        self.assertEqual(sum(batch.done.values()), 60000000)
        batch.finish(120000000)
        batch.start(b)
        batch.report(100000000, 200000000)
        self.assertIn('68%', batch.text())
        self.assertIn('220.0 / 320.0 MB', batch.text())
        self.assertIn('1/2 lezioni', batch.text())
        batch.finish(200000000)
        self.assertIn('100%', batch.text())
        self.assertIn('2/2 lezioni', batch.text())

    def test_unknown_total_is_explicit_and_failure_never_displays_complete(self):
        a, b = row('a', 'A 10 MB'), row('b', 'B')
        batch = BatchProgress([a, b])
        batch.start(a)
        batch.finish(10000000)
        self.assertIn('da determinare', batch.text())
        batch.start(b)
        batch.report(20000000, 20000000)
        self.assertIn('99%', batch.text())
        self.assertIn('1/2 lezioni', batch.text())
        batch.report(1000000, 20000000)
        self.assertIn('11.0 / 30.0 MB', batch.text())

    def test_single_and_global_progress_are_printed_together(self):
        a, b = row('a', 'A 10 MB'), row('b', 'B 20 MB')
        batch = BatchProgress([a, b])
        batch.start(a)
        output = io.StringIO()
        with redirect_stdout(output):
            report = progress_reporter(batch)
            report(10000000, 10000000)
        self.assertIn('100% · 10.0 / 10.0 MB', output.getvalue())
        self.assertIn('Totale: ≈ 33%', output.getvalue())


class BatchWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_files_failures_and_success_update_same_batch(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            class FakeCatalog:
                root = base
                errors = []
                def folder(self, record):
                    return base / record['id']
                def rows(self, course):
                    return records
                def update(self, record, status, error=None):
                    self.errors.append((record['id'], status))
            records = [row('a', 'A 1 MB'), row('b', 'B 2 MB'), row('c', 'C 3 MB')]
            batches = []
            async def download(context, catalog, record, batch=None):
                batches.append(batch)
                if record['id'] == 'b':
                    batch.report(1000000, 2000000)
                    raise DownloadError('Interrupted')
                folder = catalog.folder(record)
                folder.mkdir()
                (folder / 'video.mp4').write_bytes(b'x' * (1000000 if record['id'] == 'a' else 3000000))
                return 'present' if record['id'] == 'a' else 'downloaded'
            catalog = FakeCatalog()
            with patch('polimi_lectures.cli.download_one', new=download), redirect_stdout(io.StringIO()):
                failures = await download_rows(object(), catalog, records)
            self.assertEqual(failures, 1)
            self.assertTrue(all(batch is batches[0] for batch in batches))
            self.assertIn('5.0 / 6.0 MB', batches[0].text())
            self.assertIn('2/3 lezioni', batches[0].text())


class CatalogSizeTests(unittest.TestCase):
    def test_legacy_catalog_migrates_without_losing_rows_and_keeps_size_on_title_update(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / '.state'
            state.mkdir()
            db = sqlite3.connect(str(state / 'catalog.sqlite3'))
            db.execute('CREATE TABLE lessons (course TEXT NOT NULL,id TEXT NOT NULL,url TEXT NOT NULL,title TEXT NOT NULL,date TEXT,status TEXT NOT NULL DEFAULT "pending",path TEXT,error TEXT,PRIMARY KEY(course,id))')
            url = 'https://politecnicomilano.webex.com/recordingservice/sites/politecnicomilano/recording/playback/' + '1' * 32
            db.execute('INSERT INTO lessons(course,id,url,title,status) VALUES(?,?,?,?,?)', ('Any course', '1' * 32, url, 'Old lecture', 'complete'))
            db.commit()
            db.close()
            catalog = Catalog(temp)
            self.assertEqual(catalog.rows()[0]['status'], 'complete')
            catalog.add('Any course', url, 'New title', size_bytes=117000000)
            catalog.add('Any course', url, 'Player title without size')
            self.assertEqual(catalog.rows()[0]['size_bytes'], 117000000)
            self.assertEqual(catalog.rows()[0]['status'], 'complete')
            catalog.db.close()
