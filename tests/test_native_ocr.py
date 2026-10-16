import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
try:
    import numpy as np
    from polimi_lectures.slide_match import PageMatcher, crop_image, MATCH_VERSION
    from polimi_lectures.notebook_match import NotebookMatcher, notebook_view, visible_source, ocr_layout, layout_is_clean
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

def line(text, top, bottom):
    return dict(text=text, words=text.split(), left=10, right=900, top=top, bottom=bottom)

@unittest.skipUnless(AVAILABLE, 'Richiede slides-runtime')
class NativeOCRTests(unittest.TestCase):
    def test_native_resolution(self):
        image = np.zeros((1080, 1920, 3), np.uint8)
        self.assertEqual(crop_image(image, max_side=None).shape, (1080, 1920))
        self.assertEqual(crop_image(image).shape[1], 1100)
    def test_active_title_wins_over_tab(self):
        layout = {'lines': [line('CUDA.ipynb', 10, 30), line('PC-Challenge-1.ipynb', 100, 120),
                            line('Codice Testo Esegui tutte', 150, 170)]}
        view = notebook_view(layout, 1920, 1080)
        self.assertEqual(view['filename'], 'PC-Challenge-1.ipynb')
        self.assertGreater(view['region'][1], 170)
    def test_hidden_answers_excluded(self):
        text = visible_source('Visible question<br><!-- secret answer 1024 -->\nif (i < n)')
        self.assertNotIn('secret', text)
        self.assertNotIn('1024', text)
        self.assertIn('if (i < n)', text)
    def test_unknown_active_notebook(self):
        cells = [{'file_id':'a','file':'CUDA.ipynb','cell_index':0,'cell_id':None,
                  'kind':'code','source':'int reduction_kernel(float * input) {}'}]
        layout = {'lines': [line('CUDA.ipynb', 10, 30), line('PC-Challenge-1.ipynb', 100, 120),
                            line('Codice Testo', 150, 170)]}
        result = NotebookMatcher(cells).recognize(np.zeros((1080,1920),np.uint8),layout)
        self.assertEqual(result['status'],'unknown')
        self.assertFalse(result['notebook_ocr']['indexed'])
    def test_numeric_question_at_native_size(self):
        cells = [
            {'file_id':'a','file':'CUDA.ipynb','cell_index':60,'cell_id':None,'kind':'markdown',
             'source':'Assume 2048 elements and 1024 threads. How many warps diverge during reduction at stride 16?'},
            {'file_id':'a','file':'CUDA.ipynb','cell_index':64,'cell_id':None,'kind':'markdown',
             'source':'Assume 1024 elements. How many warps diverge at stride 16? <!-- 2048 elements and 1024 threads -->'}]
        layout = {'text':'CUDA.ipynb', 'lines':[line('CUDA.ipynb',100,120),line('Codice Testo',150,170)]}
        sizes=[]
        def layout_ocr(image):
            sizes.append(image.shape)
            return layout
        def body_ocr(image):
            sizes.append(image.shape)
            return cells[0]['source']
        with tempfile.TemporaryDirectory() as folder:
            matcher=PageMatcher({'pages':[], 'cells':cells},Path(folder))
            with patch('polimi_lectures.notebook_match.ocr_layout',side_effect=layout_ocr), \
                 patch('polimi_lectures.notebook_match.ocr',side_effect=body_ocr):
                result=matcher.recognize(np.full((1080,1920,3),70,np.uint8))
        self.assertEqual(sizes[0],(1080,1920))
        self.assertGreater(sizes[-1][1],1100)
        self.assertEqual(result['material']['cells'][0]['cell_index'],60)
        self.assertEqual(result['recognition_version'],MATCH_VERSION)
        self.assertEqual(result['ocr_mode'],'native')


@unittest.skipUnless(AVAILABLE, 'Richiede slides-runtime')
class TSVCodeTests(unittest.TestCase):
    def test_quotes_are_literal_tsv_words(self):
        header='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
        first='5\t1\t1\t1\t1\t1\t10\t10\t20\t20\t95\t"\n'
        second='5\t1\t2\t1\t1\t1\t10\t100\t100\t20\t95\tCUDA.ipynb\n'
        output=SimpleNamespace(stdout=(header+first+second).encode())
        with patch('polimi_lectures.notebook_match.subprocess.run',return_value=output):
            layout=ocr_layout(np.zeros((200,300),np.uint8))
        self.assertEqual(len(layout['lines']),2)
        self.assertEqual(layout['lines'][0]['text'],'"')
        self.assertEqual(layout['lines'][1]['text'],'CUDA.ipynb')
        self.assertTrue(layout_is_clean({'ocr':layout['text']}))
    def test_old_corrupt_metadata_is_not_a_valid_recognition(self):
        self.assertFalse(layout_is_clean({'ocr':'Text\n5\t1\t2\t180\tCUDA.ipynb'}))
        self.assertTrue(layout_is_clean({'ocr':'Text\nCUDA.ipynb'}))

    def test_title_survives_ocr_losing_filename_dot(self):
        layout={'lines':[line('CUDAipynb',100,120),line('Codice Testo',150,170)]}
        view=notebook_view(layout,1920,1080)
        self.assertEqual(view['filename'],'CUDAipynb')


@unittest.skipUnless(AVAILABLE, 'Richiede slides-runtime')
class FrameSelectionTests(unittest.TestCase):
    def test_snapshot_never_crosses_into_the_next_scene(self):
        from polimi_lectures.slide_video import interval_snapshot
        frame=SimpleNamespace(to_ndarray=lambda format: np.zeros((20,30,3),np.uint8))
        video=SimpleNamespace(snapshot=lambda t:(2.0,np.ones((20,30,3),np.uint8)),
                              frames=lambda start,end:iter([(0.8,frame)]))
        timestamp,image=interval_snapshot(video,0.0,1.0)
        self.assertEqual(timestamp,.8)
        self.assertEqual(int(image.max()),0)
    def test_no_image_outside_an_empty_interval(self):
        from polimi_lectures.slide_video import interval_snapshot
        video=SimpleNamespace(snapshot=lambda t:(2.0,np.zeros((20,30,3),np.uint8)),
                              frames=lambda start,end:iter([]))
        with self.assertRaises(ValueError):
            interval_snapshot(video,0.0,1.0)
