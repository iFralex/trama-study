import asyncio
import hashlib
import io
import json
import tempfile
import unittest
import wave
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from polimi_lectures.core import DownloadError
from polimi_lectures.local_jobs import atomic_json
from polimi_lectures.transcribe import (normalized_segments, timestamp, transcript_complete, transcribe_video,
                                       transcribe_course, OUTPUTS)
from polimi_lectures.whisper_models import (choose_model, download_model, parse_catalog, settings_path, validate_model)


class TranscriptionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.video = self.base / 'video.mp4'
        self.video.write_bytes(b'video fixture')
        self.model = self.base / 'ggml-test.bin'
        self.model.write_bytes(b'lmggmodel')
        self.directory = self.base / 'trascrizione'
        self.calls = []
        self.fail_at = None
        self.probe = patch('polimi_lectures.transcribe.probe_audio', new=AsyncMock(return_value=5))
        self.tool = patch('polimi_lectures.transcribe.run_tool', new=self.run_tool)
        self.probe.start()
        self.tool.start()
        self.addCleanup(self.probe.stop)
        self.addCleanup(self.tool.stop)

    async def run_tool(self, args, log, label):
        args = list(map(str, args))
        if args[0] == 'ffmpeg':
            length = float(args[args.index('-t') + 1])
            with wave.open(args[-1], 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b'\x00\x00' * round(length * 16000))
            self.length = length
        else:
            self.calls.append(len(self.calls))
            if self.fail_at == len(self.calls):
                raise asyncio.CancelledError()
            output = Path(args[args.index('-of') + 1]).with_suffix('.json')
            atomic_json(output, {'transcription': [{'offsets': {'from': 0, 'to': self.length * 1000}, 'text': 'Testo del blocco'}]})

    async def transcribe(self, **options):
        with redirect_stdout(io.StringIO()):
            return await transcribe_video(self.video, self.directory, self.model, options.pop('language', 'en'),
                                          'fake-whisper', chunk_seconds=2, **options)

    async def test_interruption_resumes_only_unfinished_chunks_and_keeps_global_timestamps(self):
        self.fail_at = 2
        with self.assertRaises(asyncio.CancelledError):
            await self.transcribe()
        self.assertEqual(len(list(self.directory.glob('sessioni/*/blocchi/*.json'))), 1)
        self.assertFalse(transcript_complete(self.video, self.directory))
        self.fail_at = None
        self.calls.clear()
        self.assertEqual(await self.transcribe(), 'transcribed')
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(transcript_complete(self.video, self.directory))
        data = json.loads((self.directory / 'trascrizione.json').read_text())
        self.assertEqual([s['start'] for s in data['segments']], [0, 2, 4])
        self.assertEqual([s['end'] for s in data['segments']], [2, 4, 5])
        self.assertIn('00:00:04,000 --> 00:00:05,000', (self.directory / 'trascrizione.srt').read_text())

    async def test_complete_transcription_is_skipped_without_loading_model(self):
        await self.transcribe()
        self.calls.clear()
        self.model.unlink()
        self.assertEqual(await self.transcribe(), 'present')
        self.assertEqual(self.calls, [])

    async def test_missing_or_corrupt_final_output_is_rebuilt_without_reprocessing_audio(self):
        await self.transcribe()
        (self.directory / 'trascrizione.txt').write_text('Corrupted')
        self.assertFalse(transcript_complete(self.video, self.directory))
        self.calls.clear()
        await self.transcribe()
        self.assertEqual(self.calls, [])
        self.assertTrue(transcript_complete(self.video, self.directory))

    async def test_corrupt_checkpoint_is_reprocessed_without_repeating_other_chunks(self):
        await self.transcribe()
        next(self.directory.glob('sessioni/*/blocchi/00001.json')).write_text('{broken')
        (self.directory / 'completa.json').unlink()
        self.calls.clear()
        await self.transcribe()
        self.assertEqual(len(self.calls), 1)

    async def test_changed_language_preserves_old_partial_run_and_starts_separate_checkpoints(self):
        self.fail_at = 2
        with self.assertRaises(asyncio.CancelledError):
            await self.transcribe()
        self.fail_at = None
        self.calls.clear()
        await self.transcribe(language='it')
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(len(list(self.directory.glob('sessioni/*'))), 2)

    async def test_changed_source_is_not_mistaken_for_completed_transcript(self):
        await self.transcribe()
        self.video.write_bytes(b'changed video fixture')
        self.assertFalse(transcript_complete(self.video, self.directory))
        self.calls.clear()
        await self.transcribe()
        self.assertEqual(len(self.calls), 3)

    async def test_all_complete_course_does_not_ask_for_or_download_model(self):
        await self.transcribe()
        class Catalog:
            root = self.base
            def rows(inner, course=None):
                return [{'course': 'Any subject', 'id': 'x', 'title': 'Title', 'date': None}]
            def folder(inner, row):
                return self.base
        with patch('polimi_lectures.transcribe.select_local_course', new=AsyncMock(return_value='Any subject')), \
             patch('polimi_lectures.transcribe.choose_model', new=AsyncMock(side_effect=AssertionError('Unexpected model request'))), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(await transcribe_course(Catalog(), all_pending=True), 0)


class SegmentTests(unittest.TestCase):
    def test_silent_chunk_can_complete_and_invalid_json_cannot(self):
        self.assertEqual(normalized_segments({'transcription': []}, 300, 5), [])
        for data in (None, {}, {'transcription': [{'offsets': {'from': 2000, 'to': 1000}, 'text': 'bad'}]}):
            with self.assertRaises(DownloadError):
                normalized_segments(data, 300, 5)
        self.assertEqual(timestamp(3661.123), '01:01:01,123')

    def test_relative_offsets_are_converted_and_clamped(self):
        result = normalized_segments({'transcription': [{'offsets': {'from': 1000, 'to': 5500}, 'text': ' words '}]}, 300, 5)
        self.assertEqual(result, [{'start': 301, 'end': 305, 'text': 'words'}])


class ModelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = b'lmgg' + b'x' * 100
        self.model = {'name': 'tiny', 'filename': 'ggml-tiny.bin', 'sha256': hashlib.sha256(self.payload).hexdigest(),
                      'bytes': len(self.payload), 'url': 'https://huggingface.co/model.bin'}

    def partial(self):
        directory = self.root / 'modelli/whisper'
        directory.mkdir(parents=True, exist_ok=True)
        return directory / (self.model['filename'] + '.' + self.model['sha256'][:16] + '.part')

    async def test_model_download_resumes_with_range_and_validates_checksum(self):
        self.partial().write_bytes(self.payload[:30])
        def respond(request):
            self.assertEqual(request.headers['range'], 'bytes=30-')
            return httpx.Response(206, headers={'content-range': 'bytes 30-103/104'}, content=self.payload[30:])
        with redirect_stdout(io.StringIO()):
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                target = await download_model(self.root, self.model, client)
        self.assertEqual(target.read_bytes(), self.payload)
        self.assertFalse(self.partial().exists())

    async def test_model_server_ignoring_range_restarts_safely(self):
        self.partial().write_bytes(self.payload[:30])
        with redirect_stdout(io.StringIO()):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=self.payload))) as client:
                target = await download_model(self.root, self.model, client)
        self.assertEqual(target.read_bytes(), self.payload)

    async def test_truncated_model_is_preserved_and_not_installed(self):
        with redirect_stdout(io.StringIO()):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=self.payload[:30]))) as client:
                with self.assertRaises(DownloadError):
                    await download_model(self.root, self.model, client)
        self.assertEqual(self.partial().read_bytes(), self.payload[:30])
        self.assertFalse((self.root / 'modelli/whisper/ggml-tiny.bin').exists())

    async def test_corrupt_model_is_not_installed(self):
        with redirect_stdout(io.StringIO()):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'?' * 104))) as client:
                with self.assertRaises(DownloadError):
                    await download_model(self.root, self.model, client)
        self.assertFalse((self.root / 'modelli/whisper/ggml-tiny.bin').exists())

    async def test_existing_model_path_with_spaces_is_saved(self):
        model = self.root / 'models with spaces/ggml-base.bin'
        model.parent.mkdir()
        model.write_bytes(self.payload)
        with patch('polimi_lectures.whisper_models.ask', new=AsyncMock(side_effect=['2', "'" + str(model) + "'"])), redirect_stdout(io.StringIO()):
            self.assertEqual(await choose_model(self.root), model)
        self.assertEqual(json.loads(settings_path(self.root).read_text())['model'], str(model))
        wrong = self.root / 'model.pt'
        wrong.write_bytes(b'not GGML')
        with self.assertRaises(DownloadError):
            validate_model(wrong)

    def test_catalog_accepts_only_verified_whisper_models_at_pinned_revision(self):
        data = {'sha': 'a' * 40, 'siblings': [
            {'rfilename': 'ggml-small.bin', 'lfs': {'sha256': 'b' * 64, 'size': 100}},
            {'rfilename': 'unrelated.bin', 'lfs': {'sha256': 'b' * 64, 'size': 100}},
            {'rfilename': 'ggml-tiny.bin', 'size': 100}]}
        models = parse_catalog(data)
        self.assertEqual(len(models), 1)
        self.assertIn('/resolve/' + 'a' * 40 + '/', models[0]['url'])


class WhisperIntegrationTests(unittest.TestCase):
    def test_start_offers_offline_transcription_and_keeps_menu_afterwards(self):
        from polimi_lectures.start import main
        with patch('polimi_lectures.start.load_config', return_value={'last_course': 'A GENERIC COURSE [2025-26]'}), \
             patch('polimi_lectures.start.data_root', return_value=Path('/some/disk')), \
             patch('builtins.input', side_effect=['', '2', 'q']), \
             patch('polimi_lectures.cli.main', return_value=0) as run, redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
        run.assert_called_once_with(['transcribe', '--course', 'A GENERIC COURSE [2025-26]'])

    def test_model_command_does_not_open_catalog_or_browser(self):
        from polimi_lectures.cli import main
        with patch('polimi_lectures.cli.root_path', return_value=Path('/some/disk')), \
             patch('polimi_lectures.whisper_models.choose_model', new=AsyncMock(return_value=None)), \
             patch('polimi_lectures.cli.Catalog', side_effect=AssertionError('Unexpected catalog access')), \
             patch('polimi_lectures.cli.browser_command', new=AsyncMock(side_effect=AssertionError('Unexpected browser'))):
            self.assertEqual(main(['whisper-model']), 0)

    def test_model_is_copied_and_saved_path_relocated_when_changing_data_disk(self):
        from polimi_lectures.configure import copy_archive
        with tempfile.TemporaryDirectory() as temp:
            source, destination = Path(temp) / 'old', Path(temp) / 'new'
            model = source / 'modelli/whisper/ggml-small.bin'
            model.parent.mkdir(parents=True)
            model.write_bytes(b'lmggmodel fixture')
            atomic_json(settings_path(source), {'model': str(model), 'language': 'en'})
            destination.mkdir()
            with redirect_stdout(io.StringIO()):
                self.assertTrue(copy_archive(source, destination))
            migrated = json.loads(settings_path(destination).read_text())
            self.assertEqual(migrated['model'], str(destination / 'modelli/whisper/ggml-small.bin'))
            self.assertEqual(Path(migrated['model']).read_bytes(), model.read_bytes())
            self.assertEqual(json.loads(settings_path(source).read_text())['model'], str(model))


class EngineSelectionTests(unittest.TestCase):
    def test_native_homebrew_is_preferred_even_when_python_runs_under_rosetta(self):
        from polimi_lectures.whisper_models import engine_path
        with patch('polimi_lectures.whisper_models.platform.system', return_value='Darwin'), \
             patch('polimi_lectures.whisper_models.platform.machine', return_value='x86_64'), \
             patch('polimi_lectures.whisper_models.shutil.which', return_value='/usr/local/bin/whisper-cli'), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('polimi_lectures.whisper_models.os.access', return_value=True):
            self.assertEqual(engine_path(), '/opt/homebrew/bin/whisper-cli')
            self.assertEqual(engine_path('/custom/whisper-cli'), '/custom/whisper-cli')
