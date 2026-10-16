import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

try:
    import av
    import cv2
    import numpy as np
    import pymupdf
    
    from polimi_lectures.local_jobs import atomic_json, file_hash
    from polimi_lectures.slide_index import index_materials, image_write
    from polimi_lectures.slide_match import PageMatcher
    from polimi_lectures.slide_video import Video, align_video, digest, attach_transcript, refine_boundary
    VISUAL_AVAILABLE = True
except ImportError:
    VISUAL_AVAILABLE = False


@unittest.skipUnless(VISUAL_AVAILABLE, "Eseguire con .state/slides-runtime/bin/python")
class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='polimi-slide-tests-', dir=None)
        cls.root = Path(cls.temp.name)
        cls.materials = cls.root / 'materiali'
        cls.materials.mkdir()
        pdf = pymupdf.open()
        for i, title in enumerate(('PARALLEL REDUCTION ALGORITHM', 'CUDA MEMORY COALESCING')):
            page = pdf.new_page(width=960, height=540)
            page.insert_text((45, 65), title, fontsize=30)
            body = ('Each processor combines local values through a binary reduction tree.\n'
                    'Associative operations enable logarithmic complexity and linear work.\n'
                    'Synchronization barriers separate consecutive stages of the computation.' if i == 0 else
                    'Adjacent threads access contiguous addresses in global device memory.\n'
                    'Aligned transactions reduce bandwidth waste and memory latency.\n'
                    'Shared memory tiles improve reuse for matrix multiplication kernels.')
            page.insert_text((45, 120), body, fontsize=18)
            rng = np.random.default_rng(15 + i)
            for n in range(35):
                x, y = rng.integers(50, 860), rng.integers(230, 480)
                page.draw_rect(pymupdf.Rect(int(x), int(y), int(x+35), int(y+20)), color=(0,0,0), width=2)
                page.insert_text((int(x+2),int(y+15)), str(n+i*100), fontsize=10)
            page.insert_text((900,520), str(i+1), fontsize=12)
        pdf.save(cls.materials/'slides.pdf')
        pdf.close()
        atomic_json(cls.materials/'CUDA.ipynb', {'nbformat':4, 'cells':[{'cell_type':'code', 'source':['print("hello")'], 'outputs':[]}]})
        cls.index_dir = cls.root/'indice'
        cls.index = index_materials(cls.materials, cls.index_dir, lambda s: None)
        cls.images = [cv2.cvtColor(cv2.imread(str(cls.index_dir/p['image']),0),cv2.COLOR_GRAY2BGR) for p in cls.index['pages']]
        # Native variable frame timestamps, including a deliberately uneven gap.
        cls.video = cls.root/'video.mp4'
        container = av.open(str(cls.video),'w')
        stream = container.add_stream('libx264', rate=10)
        stream.width, stream.height = 960, 540
        stream.pix_fmt='yuv420p'
        stream.time_base=Fraction(1,1000)
        stream.codec_context.time_base=Fraction(1,1000)
        cls.times = [n*100 for n in range(100) if n not in (29,30,59)]
        for t in cls.times:
            source = cls.images[0 if t<3100 else 1] if t<6100 else np.zeros_like(cls.images[0])
            frame=av.VideoFrame.from_ndarray(cv2.resize(source,(960,540)),format='bgr24')
            frame.pts=t
            frame.time_base=Fraction(1,1000)
            for packet in stream.encode(frame): container.mux(packet)
        for packet in stream.encode(): container.mux(packet)
        container.close()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_01_index_resume_and_notebook(self):
        self.assertEqual(len(self.index['pages']),2)
        self.assertEqual(len(self.index['cells']),1)
        paths=[self.index_dir/p['image'] for p in self.index['pages']]
        old=[p.stat().st_mtime_ns for p in paths]
        repeated=index_materials(self.materials,self.index_dir,lambda s:None)
        self.assertEqual(repeated['identity'],self.index['identity'])
        self.assertEqual(old,[p.stat().st_mtime_ns for p in paths])
        self.assertFalse(self.index['issues'])
        cached=self.index_dir/self.index['pages'][0]['features']
        cached.write_bytes(b'corrotto')
        repaired=index_materials(self.materials,self.index_dir,lambda s:None)
        with np.load(cached,allow_pickle=False) as values:
            self.assertGreater(len(values['points']),12)
        self.assertEqual(repaired['identity'],self.index['identity'])

    def test_02_recognize_scaled_slide_and_unknown(self):
        matcher=PageMatcher(self.index,self.index_dir)
        for i,image in enumerate(self.images):
            screenshot=np.full((720,1280,3),35,np.uint8)
            screenshot[60:660,90:1190]=cv2.resize(image,(1100,600))
            screenshot[620:710,1150:1270]=70
            result=matcher.recognize(screenshot)
            self.assertEqual(result['status'],'matched',result)
            self.assertEqual(result['material']['page'],i+1)
        self.assertEqual(matcher.recognize(np.zeros((540,960,3),np.uint8))['status'],'unknown')

    def test_03_variable_pts_and_refinement(self):
        video=Video(self.video)
        try:
            actual=[round(t*1000) for t,f in video.frames(0,10)]
            self.assertEqual(actual,self.times)
            self.assertTrue(len(set(b-a for a,b in zip(actual,actual[1:])))>1)
            time,error=refine_boundary(video,2,4,[0,0,960,540])
            self.assertAlmostEqual(time,3.1,places=3)
            self.assertLessEqual(error,.31)
        finally: video.close()

    def test_04_interruption_resume_exports_and_transcript(self):
        out=self.root/'allineamento'
        original=PageMatcher.recognize
        calls=[]
        def interrupted(matcher,*args,**kwargs):
            calls.append(1)
            if len(calls)==2: raise RuntimeError('interruzione simulata')
            return original(matcher,*args,**kwargs)
        with patch.object(PageMatcher,'recognize',interrupted):
            with self.assertRaisesRegex(RuntimeError,'simulata'):
                align_video(self.video,out,self.index,self.index_dir,step=1,progress=lambda s:None)
        checkpoints=list(out.glob('sessioni/*/riconoscimenti/*.json'))
        self.assertEqual(len(checkpoints),1)
        timestamp=checkpoints[0].stat().st_mtime_ns
        with patch('polimi_lectures.slide_video.scan_window',side_effect=AssertionError('rescan')):
            result=align_video(self.video,out,self.index,self.index_dir,step=1,progress=lambda s:None)
        self.assertEqual(timestamp,checkpoints[0].stat().st_mtime_ns)
        self.assertEqual([i['status'] for i in result['intervals']],['matched','matched','unknown'])
        self.assertEqual([i.get('material',{}).get('page') if i.get('material') else None for i in result['intervals']],[1,2,None])
        self.assertTrue(all(i['start'] <= i['frame_time'] < i['end'] for i in result['intervals']))
        self.assertAlmostEqual(result['intervals'][1]['start'],3.1,places=3)
        self.assertAlmostEqual(result['intervals'][2]['start'],6.1,places=3)
        with patch.object(PageMatcher,'recognize',side_effect=AssertionError('re-recognition')):
            skipped=align_video(self.video,out,self.index,self.index_dir,step=1,progress=lambda s:None)
            self.assertEqual(skipped,result)
            (out/'allineamento.csv').write_text('corrotto')
            repaired=align_video(self.video,out,self.index,self.index_dir,step=1,progress=lambda s:None)
            self.assertEqual(repaired,result)
            atomic_json(self.root/'trascrizione/trascrizione.json',{'identity':{'video_sha256':file_hash(self.video)},'segments':[
                {'start':2.9,'end':3.3,'text':'segmento attraversa il cambio'}]})
            joined=align_video(self.video,out,self.index,self.index_dir,step=1,progress=lambda s:None)
            self.assertEqual(joined['transcript_state'],'complete')
            self.assertEqual(joined['intervals'][0]['transcript'][0]['text'],joined['intervals'][1]['transcript'][0]['text'])
            self.assertEqual(joined['intervals'][0]['transcript'][0]['overlap_end'],3.1)

        # Upgrade recognizer while preserving scans and source frames.
        marker=json.loads((out/'completo.json').read_text())
        marker['recognition_version']=1
        atomic_json(out/'completo.json',marker)
        for checkpoint in out.glob('sessioni/*/riconoscimenti/*.json'):
            record=json.loads(checkpoint.read_text())
            record['recognition_version']=1
            atomic_json(checkpoint,record)
        with patch('polimi_lectures.slide_video.scan_window',side_effect=AssertionError('rescan')), \
             patch.object(Video,'snapshot',side_effect=AssertionError('decode cached frame')), \
             patch.object(PageMatcher,'recognize',autospec=True,side_effect=original) as recognition:
            upgraded=align_video(self.video,out,self.index,self.index_dir,step=1,progress=lambda s:None)
        self.assertEqual(recognition.call_count,3)
        self.assertEqual(upgraded['recognition_version'],2)

        # A cached timestamp outside the final interval must be repaired.
        first=sorted(out.glob('sessioni/*/riconoscimenti/*.json'))[0]
        record=json.loads(first.read_text())
        record['frame_time']=100.0
        atomic_json(first,record)
        (out/'allineamento.csv').write_text('force rebuild')
        with patch('polimi_lectures.slide_video.scan_window',side_effect=AssertionError('rescan')), \
             patch.object(PageMatcher,'recognize',autospec=True,side_effect=original) as recognition:
            repaired=align_video(self.video,out,self.index,self.index_dir,step=1,progress=lambda s:None)
        self.assertEqual(recognition.call_count,1)
        self.assertTrue(all(i['start'] <= i['frame_time'] < i['end'] for i in repaired['intervals']))

    def test_05_duplicate_sources_ambiguous(self):
        # Same visual content, different source IDs: must retain alternatives.
        index=dict(self.index)
        duplicate=dict(index['pages'][0],id='other:page:1',file='copy.pdf',content_key='different')
        index['pages']=index['pages']+[duplicate]
        result=PageMatcher(index,self.index_dir).recognize(self.images[0])
        self.assertEqual(result['status'],'ambiguous',result)
        self.assertIsNone(result['material'])
        self.assertGreaterEqual(len(result['alternatives']),2)


if __name__=='__main__': unittest.main(verbosity=2)
