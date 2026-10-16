import json
import tempfile
import unittest
from pathlib import Path

from polimi_lectures.config import data_root, load_config
from polimi_lectures.configure import ConfigurationError, configure, parse_folder
from polimi_lectures.core import Catalog


URL = 'https://politecnicomilano.webex.com/recordingservice/sites/politecnicomilano/recording/playback/0123456789abcdef0123456789abcdef'


class ConfigurationTests(unittest.TestCase):
    def test_new_setup_saves_email_and_destination_with_spaces(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / 'app'
            destination = Path(folder) / 'Disco con spazi' / 'Lezioni'
            project.mkdir()
            self.assertFalse(configure(project, 'student@example.edu', destination))
            self.assertEqual(load_config(project)['email'], 'student@example.edu')
            self.assertEqual(data_root(project=project), destination.resolve())
            self.assertEqual((project / '.state/settings.json').stat().st_mode & 0o777, 0o600)

    def test_existing_archive_is_copied_and_browser_session_stays_local(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / 'app'
            project.mkdir()
            catalog = Catalog(project)
            catalog.add('Parallel Computing', URL, 'Lezione MPI', '2026-10-14')
            row = catalog.rows()[0]
            video_dir = catalog.folder(row)
            video_dir.mkdir(parents=True)
            (video_dir / 'video.mp4').write_bytes(b'fixture')
            relative = video_dir.relative_to(project)
            catalog.update(row, 'complete', relative)
            catalog.db.close()
            profile = project / '.state/browser'
            profile.mkdir()
            (profile / 'session-fixture').write_text('session')
            (project / '.state/auth-state.json').write_text('auth-fixture')
            binaries = project / '.state/browsers'
            binaries.mkdir()
            (binaries / 'not-data').write_text('browser-binary')
            destination = Path(folder) / 'external #1' / 'Lezioni'
            self.assertTrue(configure(project, 'student@example.edu', destination))
            moved = Catalog(destination)
            self.assertEqual(moved.rows()[0]['status'], 'complete')
            self.assertEqual((moved.folder(moved.rows()[0]) / 'video.mp4').read_bytes(), b'fixture')
            moved.db.close()
            self.assertTrue((project / relative / 'video.mp4').exists())
            self.assertEqual((project / '.state/browser/session-fixture').read_text(), 'session')
            self.assertFalse((destination / '.state/browser').exists())
            self.assertFalse((destination / '.state/auth-state.json').exists())
            self.assertFalse((destination / '.state/browsers').exists())

    def test_conflicting_destination_is_not_overwritten_and_config_is_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / 'app'
            project.mkdir()
            configure(project, 'first@example.edu', project)
            catalog = Catalog(project)
            catalog.add('Parallel Computing', URL)
            catalog.db.close()
            old = load_config(project)
            destination = Path(folder) / 'external'
            (destination / '.state').mkdir(parents=True)
            sentinel = destination / '.state/keep'
            sentinel.write_text('existing')
            with self.assertRaises(ConfigurationError):
                configure(project, 'second@example.edu', destination)
            self.assertEqual(load_config(project), old)
            self.assertEqual(sentinel.read_text(), 'existing')

    def test_invalid_email_and_unmounted_external_disk_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            with self.assertRaises(ConfigurationError):
                configure(project, 'not-an-email', project / 'data')
            missing = Path('/Volumes/POLIMI-TEST-DISCO-NON-MONTATO/Lezioni')
            with self.assertRaises(ConfigurationError):
                configure(project, 'student@example.edu', missing)
            self.assertFalse(missing.exists())

    def test_missing_configured_data_does_not_create_an_empty_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / '.state').mkdir()
            missing = project / 'missing'
            (project / '.state/settings.json').write_text(json.dumps({'data_dir': str(missing)}))
            with self.assertRaises(ValueError):
                data_root(project=project)
            self.assertFalse(missing.exists())

    def test_quoted_and_finder_escaped_paths(self):
        self.assertEqual(parse_folder("'/tmp/Disco con spazi/Lezioni'"), Path('/tmp/Disco con spazi/Lezioni').resolve())
        self.assertEqual(parse_folder('/tmp/Disco\\ con\\ spazi/Lezioni'), Path('/tmp/Disco con spazi/Lezioni').resolve())

    def test_destination_inside_existing_course_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            catalog = Catalog(project)
            catalog.add('Parallel Computing', URL)
            catalog.db.close()
            with self.assertRaises(ConfigurationError):
                configure(project, 'student@example.edu', project / 'corsi/nested')
