"""Local study store and JSON-lines bridge. Original course files are read-only."""
import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import uuid
import struct
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .config import data_root, load_config
from .study_beginner import BeginnerStudy
from .study_course import CourseStudy
from .study_preparation import PreparationStudy


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def encoded(value):
    return json.dumps(value, ensure_ascii=False)


def key(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


CONCEPTS = {
    'pram': ('PRAM e accessi concorrenti', ['PRAM', 'EREW', 'CREW', 'CRCW', 'concurrent', 'exclusive'], []),
    'reduction': ('Riduzione parallela', ['reduction', 'riduzione', 'sum', 'tree', 'somma'], ['pram']),
    'scan': ('Prefix sum', ['prefix', 'scan', 'prefissi'], ['reduction']),
    'scaling': ('Speedup ed efficienza', ['speedup', 'efficiency', 'amdahl', 'gustafson', 'efficienza'], ['pram']),
    'simd': ('SIMD e divergenza', ['SIMD', 'divergence', 'divergenza', 'vectorization'], []),
    'memory': ('Memoria e bandwidth', ['bandwidth', 'coalescing', 'coalesced', 'latency', 'memoria'], []),
    'synchronization': ('Sincronizzazione', ['synchronization', 'barrier', 'race', 'consistency', 'sincronizzazione'], []),
    'openmp': ('OpenMP', ['openmp', 'pragma', 'schedule'], ['synchronization']),
}

TRANSLATIONS={'riduzione':'reduction','parallela':'parallel','parallelo':'parallel','prefissi':'prefix',
 'legge':'law','divergenza':'divergence','consistenza':'consistency','sincronizzazione':'synchronization',
 'coalescenti':'coalesced','coalescenza':'coalescing','memoria':'memory','latenza':'latency',
 'efficienza':'efficiency','processori':'processors','letture':'read','scritture':'write',
 'somma':'sum','modelli':'models','accessi':'access'}


class _StudyBase(BeginnerStudy, CourseStudy):
    def __init__(self, root, database=None):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError('Disco dati non disponibile.')
        state = self.root / '.state' / 'studio'
        state.mkdir(parents=True, exist_ok=True)
        self.state = state
        self.db = sqlite3.connect(str(database or state / 'studio.sqlite3'))
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,course TEXT,path TEXT,fingerprint TEXT,issue TEXT);
          CREATE TABLE IF NOT EXISTS passages(id TEXT PRIMARY KEY,document TEXT,course TEXT,kind TEXT,title TEXT,path TEXT,
            page INTEGER,start REAL,end REAL,text TEXT,quality TEXT,reserved INTEGER DEFAULT 0,solution INTEGER DEFAULT 0,metadata TEXT);
          CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED,course UNINDEXED,title,text,tokenize='unicode61');
          CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,course TEXT,goal TEXT,minutes INTEGER,stage INTEGER,mode TEXT,
            current TEXT,created TEXT,updated TEXT);
          CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,session TEXT,role TEXT,text TEXT,created TEXT);
          CREATE TABLE IF NOT EXISTS activities(id TEXT,version INTEGER,session TEXT,spec TEXT,state TEXT,created TEXT,
            PRIMARY KEY(id,version));
          CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,session TEXT,activity TEXT,version INTEGER,kind TEXT,payload TEXT,created TEXT);
          CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,event TEXT UNIQUE,session TEXT,activity TEXT,version INTEGER,
            concept TEXT,answer TEXT,grade TEXT,aids INTEGER,created TEXT,correction TEXT);
          CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,course TEXT,concept TEXT,due TEXT,card TEXT,last_attempt TEXT);
          CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
          CREATE TABLE IF NOT EXISTS vectors(source TEXT,chunk INTEGER,model TEXT,fingerprint TEXT,vector BLOB,
            PRIMARY KEY(source,chunk,model));
          CREATE INDEX IF NOT EXISTS passages_course ON passages(course);
          CREATE INDEX IF NOT EXISTS events_activity ON events(activity,version);
        ''')
        self.db.commit()
        self.setup_beginner()
        self.setup_course_study()
        self.setup_preparation()

    def courses(self):
        base = self.root / 'corsi'
        if not base.exists():
            return []
        result = []
        labels = {}
        catalog = self.root / '.state/catalog.sqlite3'
        if catalog.exists():
            with sqlite3.connect('file:%s?mode=ro' % catalog, uri=True) as db:
                from .core import slug
                labels = {slug(row[0]): row[0] for row in db.execute('SELECT DISTINCT course FROM lessons')}
        for folder in sorted(base.iterdir()):
            if folder.is_dir() and (folder / 'materiali').is_dir():
                result.append({'id': folder.name, 'label': labels.get(folder.name, folder.name.replace('-', ' '))})
        return result

    def course_path(self, course):
        if course not in {c['id'] for c in self.courses()}:
            raise ValueError('Corso non disponibile.')
        return self.root / 'corsi' / course

    def setting(self, name, value=None):
        if name not in ('model', 'last_course', 'installation_id', 'preparation_routing'):
            raise ValueError('Impostazione non valida.')
        if value is not None:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (name, encoded(value)))
            self.db.commit()
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (name,)).fetchone()
        return json.loads(row[0]) if row else None

    def installation_id(self):
        value=self.setting('installation_id')
        try:
            if str(uuid.UUID(str(value)))==str(value).lower():return value
        except (ValueError,AttributeError,TypeError):pass
        value=str(uuid.uuid4())
        self.setting('installation_id',value)
        return value

    def bootstrap(self):
        courses = self.courses()
        from .core import slug
        preferred = self.setting('last_course') or slug(load_config().get('last_course', ''))
        selected = next((c['id'] for c in courses if c['id'] == preferred), courses[0]['id'] if courses else None)
        return {'courses': courses, 'selected': selected, 'model': self.setting('model'), 'state_dir': str(self.state), 'recommendation':self.recommendation(selected) if selected else None}

    def import_course(self, course):
        import pymupdf
        base = self.course_path(course)
        materials = base / 'materiali'
        pdfs = sorted(materials.rglob('*.pdf'))
        exams = [p for p in pdfs if re.search(r'1st-part', p.name, re.I) and '.sol.' not in p.name]
        holdout = exams[-1].name.replace('.pdf', '') if exams else None
        files = pdfs + sorted(materials.rglob('*.ipynb')) + sorted(base.glob('*/trascrizione/trascrizione.json'))
        files += sorted(base.glob('*/allineamento/allineamento.json'))
        text_types={'.html','.htm','.txt','.md','.py','.c','.cpp','.h','.hpp','.cu','.java','.m','.r'}
        files += sorted(p for p in materials.rglob('*') if p.is_file() and p.suffix.lower() in text_types)
        changed, issues, present = 0, [], []
        for path in files:
            relative = str(path.relative_to(self.root))
            did = key(relative)
            present.append(did)
            stat = path.stat()
            fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
            if path.name=='trascrizione.json':
                fingerprint += ':complete='+str((path.parent/'completa.json').exists())
            old = self.db.execute('SELECT fingerprint,issue FROM documents WHERE id=?', (did,)).fetchone()
            if old and old['fingerprint'] == fingerprint and not old['issue']:
                continue
            records = []
            try:
                solution = int('.sol.' in path.name)
                reserved = int(bool(holdout and path.name.replace('.sol.pdf', '').replace('.pdf', '') == holdout))
                meta = {}
                if path.suffix == '.pdf':
                    doc = pymupdf.open(path)
                    header = doc[0].get_text()[:400] if len(doc) else ''
                    stamp = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+\w*,?\s+20\d\d', header)
                    file_date = re.search(r'-(\d{2})-(\d{2})-(\d{2})(?:\.sol)?\.pdf$', path.name)
                    if stamp and file_date:
                        header_date = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', stamp[0])
                        header_date = datetime.strptime(header_date.replace(',', ''), '%B %d %Y')
                        expected = '20%s-%s-%s' % file_date.groups()
                        if header_date.strftime('%Y-%m-%d') != expected:
                            meta['issue'] = 'Data discordante: nome file %s; intestazione %s.' % (expected, stamp[0])
                            issues.append({'file': path.name, 'message': meta['issue']})
                    for i, page in enumerate(doc):
                        text = page.get_text(sort=True).strip()
                        if text:
                            records.append((i, 'pdf', text, i+1, None, None, 'originale', dict(meta)))
                    doc.close()
                elif path.suffix == '.ipynb':
                    notebook = json.loads(path.read_text())
                    for i, cell in enumerate(notebook.get('cells', [])):
                        text = cell.get('source', '')
                        text = ''.join(text) if isinstance(text, list) else text
                        text = re.sub(r'<!--[\s\S]*?-->', '', text)
                        if text.strip():
                            records.append((i, 'notebook', text, i, None, None, 'originale', {'cell_kind': cell.get('cell_type')}))
                elif path.suffix.lower() in text_types:
                    text=path.read_text(encoding='utf-8',errors='replace')
                    if path.suffix.lower() in ('.html','.htm'):
                        from html import unescape
                        text=re.sub(r'<(script|style)\b[^>]*>[\s\S]*?</\1>', '', text, flags=re.I)
                        text=re.sub(r'<!--[\s\S]*?-->', '', text)
                        text=unescape(re.sub(r'<[^>]+>', '\n', text))
                    lines=text.splitlines()
                    for i in range(0,len(lines),100):
                        part='\n'.join(lines[i:i+100]).strip()
                        if part:records.append((i,'text',part,None,None,None,'originale',{'first_line':i+1}))
                elif path.name == 'trascrizione.json':
                    transcript = json.loads(path.read_text())
                    quality = 'trascrizione completa' if (path.parent/'completa.json').exists() else 'trascrizione parziale'
                    segments = transcript.get('segments', [])
                    for i in range(0, len(segments), 12):
                        group = segments[i:i+12]
                        records.append((i, 'video', ' '.join(s['text'] for s in group), None, group[0]['start'], group[-1]['end'], quality, {}))
                else:
                    alignment = json.loads(path.read_text())
                    for i, interval in enumerate(alignment.get('intervals', [])):
                        if not interval.get('material') and not interval.get('notebook'):
                            continue
                        text = interval.get('ocr', '')
                        if text.strip():
                            records.append((i, 'alignment', text, None, interval['start'], interval['end'],
                                            str(interval.get('confidence', 'candidato')), {'alignment': interval}))
                with self.db:
                    previous_ids = [r[0] for r in self.db.execute('SELECT id FROM passages WHERE document=?', (did,))]
                    self.db.executemany('DELETE FROM search WHERE id=?', [(s,) for s in previous_ids])
                    self.db.execute('DELETE FROM passages WHERE document=?', (did,))
                    for number, kind, text, page, start, end, quality, metadata in records:
                        pid = '%s:%s' % (did, number)
                        title = path.name if kind in ('pdf','notebook','text') else path.parent.parent.name[:105]
                        self.db.execute('INSERT INTO passages VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (pid,did,course,kind,title,relative,page,start,end,text,quality,reserved,solution,encoded(metadata)))
                        self.db.execute('INSERT INTO search VALUES(?,?,?,?)', (pid,course,title,text))
                    self.db.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?)', (did,course,relative,fingerprint,None))
                changed += 1
            except (ValueError, OSError, RuntimeError) as exc:
                issues.append({'file': path.name, 'message': str(exc)[:200]})
                with self.db:
                    self.db.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?)', (did,course,relative,fingerprint,str(exc)[:200]))
        # Remove deleted sources from retrieval, retaining study attempts and citations.
        obsolete = [r[0] for r in self.db.execute('SELECT id FROM documents WHERE course=?', (course,)) if r[0] not in present]
        with self.db:
            for did in obsolete:
                self.db.execute('DELETE FROM search WHERE id IN (SELECT id FROM passages WHERE document=?)', (did,))
                self.db.execute('DELETE FROM passages WHERE document=?', (did,))
                self.db.execute('DELETE FROM documents WHERE id=?', (did,))
        self.course_apply_reservations(course)
        return {'changed':changed, 'passages': self.db.execute('SELECT count(*) FROM passages WHERE course=?',(course,)).fetchone()[0], 'issues':issues}

    def source(self, source_id, allow_reserved=False, allow_solutions=True):
        row = self.db.execute('SELECT p.* FROM passages p JOIN documents d ON d.id=p.document WHERE p.id=? AND d.issue IS NULL',(source_id,)).fetchone()
        if not row or (row['reserved'] and not allow_reserved) or (row['solution'] and not allow_solutions):
            raise ValueError('Fonte non disponibile durante questa attività.')
        result = dict(row)
        result['metadata'] = json.loads(result['metadata'])
        result['context']=[dict(r) for r in self.db.execute('SELECT id,text,page,start,end FROM passages WHERE document=? AND id!=? ORDER BY abs(COALESCE(page,start)-?) LIMIT 2',(row['document'],row['id'],row['page'] if row['page'] is not None else row['start']))]
        return result

    def render_pdf(self,source_id,allow_reserved=False,allow_solutions=True):
        import pymupdf
        source=self.source(source_id,allow_reserved,allow_solutions)
        if source['kind']!='pdf':
            raise ValueError('La fonte non è un PDF.')
        file=(self.root/source['path']).resolve()
        if self.root not in file.parents or not file.is_file():
            raise ValueError('PDF non disponibile sul disco dati.')
        fingerprint=self.db.execute('SELECT fingerprint FROM documents WHERE id=?',(source['document'],)).fetchone()[0]
        directory=self.state/'pages'
        directory.mkdir(exist_ok=True)
        output=directory/(key(fingerprint+':'+str(source['page']))+'.png')
        if not output.exists():
            with pymupdf.open(file) as doc:
                pixmap=doc[source['page']-1].get_pixmap(matrix=pymupdf.Matrix(1.7,1.7),alpha=False)
                temporary=output.with_suffix('.tmp.png')
                pixmap.save(temporary)
                temporary.replace(output)
        return {'path':str(output)}

    def search(self, course, query, limit=8, mode='learn'):
        self.course_path(course)
        words = re.findall(r'[\w]{3,}', str(query).casefold())[:30]
        stop = {'come','della','delle','quale','sono','spiega','spiegami','perché','perche','con','una','the','and','for','differenza','tra','degli','dei'}
        words = [w for w in words if w not in stop]
        words=[TRANSLATIONS.get(w,w) for w in words]
        if words==['pram']:
            words.extend(['EREW','CREW','CRCW'])
        expression = ' OR '.join('"%s"'%w.replace('"','') for w in dict.fromkeys(words))
        if not expression:
            return []
        rows = self.db.execute('''SELECT p.*,bm25(search) rank FROM search JOIN passages p ON p.id=search.id JOIN documents d ON d.id=p.document
          WHERE search MATCH ? AND p.course=? AND p.reserved=0 AND d.issue IS NULL AND (?!='exam' OR p.solution=0)
          ORDER BY rank LIMIT 100''',(expression,course,mode)).fetchall()
        specific={'pram','reduction','prefix','consistency','amdahl','gustafson','coalesced','coalescing','divergence','synchronization','erew','crew','crcw','openmp'}
        terms=set(w.casefold() for w in words)
        def score(row):
            text=row['text'].casefold()
            matched=terms & set(re.findall(r'\w+',text))
            syllabus=any(word in row['title'].casefold() for word in ('plan-didattica','syllabus','programma'))
            return 20*len(matched & specific)+2*len(matched-specific)+(-row['rank'])*.1+(0.5 if row['kind']=='pdf' else 0)-(25 if syllabus else 0)
        ranked=sorted(rows,key=score,reverse=True)
        output=[]
        documents={}
        for row in ranked:
            if documents.get(row['document'],0)>=3:
                continue
            documents[row['document']]=documents.get(row['document'],0)+1
            output.append(dict(row,metadata=json.loads(row['metadata'])))
            if len(output)>=max(1,min(int(limit),20)):
                break
        return output

    def session(self, sid):
        row = self.db.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone()
        if not row:
            raise ValueError('Sessione non trovata.')
        return dict(row)

    def message(self, session, role, text):
        self.session(session)
        if role not in ('user','assistant','system'):
            raise ValueError('Ruolo non valido.')
        if not str(text).strip():
            return None
        mid=uid()
        with self.db:
            self.db.execute('INSERT INTO messages VALUES(?,?,?,?,?)',(mid,session,role,str(text)[:100000],now()))
            self.db.execute('UPDATE sessions SET updated=? WHERE id=?',(now(),session))
        return mid

    def open_session(self, course, goal='Capire e saper risolvere', minutes=25, mode='learn', fresh=False, approach='standard'):
        self.course_path(course)
        if mode not in ('learn','exam'):
            raise ValueError('Modalità non valida.')
        if approach not in ('standard','beginner') or (mode=='exam' and approach=='beginner'):
            raise ValueError('Modalità di apprendimento non valida.')
        lessons=self.course_lessons(course) if approach=='beginner' else []
        if approach=='beginner' and not lessons:raise ValueError('Importa prima almeno una trascrizione o un materiale didattico del corso.')
        self.setting('last_course',course)
        row = None if fresh else self.db.execute('SELECT id FROM sessions WHERE course=? AND mode=? ORDER BY updated DESC LIMIT 1',(course,mode)).fetchone()
        if row and approach=='beginner':
            row=self.db.execute('SELECT s.id FROM sessions s JOIN beginner_sessions b ON b.session=s.id WHERE s.course=? ORDER BY s.updated DESC LIMIT 1',(course,)).fetchone()
        if row:
            return self.view(row['id'])
        sid=uid()
        with self.db:
            self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?)',(sid,course,str(goal)[:200],max(5,min(int(minutes),180)),0,mode,None,now(),now()))
        if approach=='beginner':
            with self.db:self.db.execute('INSERT INTO beginner_sessions VALUES(?,?)',(sid,lessons[0]['id']))
            self.message(sid,'assistant','Partiamo dalle tue lezioni, senza dare per scontati i prerequisiti. Ogni argomento avrà spiegazioni, esempi e prove collegate alle fonti. Puoi scegliere un’altra lezione o chiedere di rallentare.')
            return self.view(sid)
        self.message(sid,'assistant','Partiamo da una prova breve. Puoi chiedere una spiegazione o cambiare argomento in qualsiasi momento.' if mode=='learn' else 'Simulazione autonoma: rispondi senza aiuti. La correzione sarà disponibile alla consegna.')
        self.seed(sid)
        return self.view(sid)

    def create_activity(self, sid, spec, activity_id=None, chapter=None):
        session=self.session(sid)
        if session['mode']=='exam':
            raise ValueError('Durante la simulazione non si aggiungono attività generate.')
        curriculum=self._path_for_session(sid)
        if curriculum:
            target=chapter or curriculum['chapter']
            if not target or target not in {c['id'] for c in self._plan(curriculum['path'])['data']['chapters']}:raise ValueError('Apri prima un capitolo valido del percorso.')
            self._refs(session['course'],spec.get('sources'))
            if spec.get('kind')!='explain' and not all(spec.get(k) for k in ('solution','rubric','origin','assumptions')):raise ValueError('Prepara soluzione e criteri prima di proporre un esercizio.')
            if spec.get('kind')=='html' and not all(spec.get(k) for k in ('model','fallback')):raise ValueError('Dichiara modello e alternativa testuale del laboratorio.')
            spec=dict(spec,concept=curriculum['path']+':'+target,curriculum={'path':curriculum['path'],'chapter':target,'extra':True})
        learning=self.beginner_context(sid)
        if learning:
            if not learning['current_unit']:raise ValueError('Prepara prima un piano fondato sulle fonti della lezione con set_lesson_plan.')
            refs=spec.get('sources',[])
            if not set(refs)&set(learning['current_unit']['sources']):raise ValueError('L’attività deve citare almeno una fonte dell’argomento corrente.')
            spec=dict(spec,concept=learning['current_unit']['id'],beginner={'lesson':learning['lesson']['id'],'unit':learning['unit_index'],'phase':learning['phase']})
        return self._activity(sid,dict(spec,grading_origin='generated'),activity_id)

    def _activity(self,sid,spec,activity_id=None):
        if spec.get('kind') not in ('choice','numeric','open','completion','explain','html'):
            raise ValueError('Tipo attività non valido.')
        if len(encoded(spec))>180000:
            raise ValueError('Attività troppo grande.')
        session=self.session(sid)
        refs=[]
        for ref in spec.get('sources',[]):
            source=self.source(ref,allow_reserved=session['mode']=='exam',allow_solutions=session['mode']!='exam')
            if source['course']!=session['course']:
                raise ValueError('Fonte di un altro corso.')
            refs.append(ref)
        spec=dict(spec,sources=refs,grading_origin=spec.get('grading_origin','curated'))
        aid=activity_id or uid()
        previous=self.db.execute('SELECT * FROM activities WHERE id=? ORDER BY version DESC LIMIT 1',(aid,)).fetchone()
        if previous and previous['session']!=sid:
            raise ValueError('Attività di un’altra sessione.')
        version=(previous['version']+1) if previous else 1
        state=json.loads(previous['state']) if previous else {}
        with self.db:
            self.db.execute('INSERT INTO activities VALUES(?,?,?,?,?,?)',(aid,version,sid,encoded(spec),encoded(state),now()))
            self.db.execute('UPDATE sessions SET current=?,updated=? WHERE id=?',(aid+'@'+str(version),now(),sid))
        return {'id':aid,'version':version}

    def seed(self,sid):
        s=self.session(sid)
        if s['mode']=='exam':
            rows=self.db.execute("SELECT id,text FROM passages WHERE course=? AND reserved=1 AND solution=0 AND kind='pdf' ORDER BY page",(s['course'],)).fetchall()
            spec={'kind':'open','title':'Prova autonoma · tema riservato','prompt':'\n\n'.join(r['text'] for r in rows) if rows else 'Nessun tema riservato disponibile. Importa i materiali del corso.', 'concept':'pram','sources':[r['id'] for r in rows],'rubric':'Valutazione alla consegna, con criteri espliciti.'}
            self._activity(sid,spec)
            return
        sources=self.search(s['course'],'PRAM EREW CREW',6)
        # A course without PRAM gets a general reading path, never another course's content.
        has_pram=any('pram' in r['text'].lower() for r in sources)
        if not has_pram:
            self._activity(sid,{'kind':'explain','title':'Scegli il tuo obiettivo','prompt':'Chiedi al tutor un argomento del tuo corso. Cercherà le fonti e preparerà un’attività collegata.','sources':[],'concept':'general'})
            return
        from .study_content import pathway
        specs=pathway()
        spec=specs[min(s['stage'],len(specs)-1)]
        concept=spec.get('concept','pram')
        seed_queries={'pram':'EREW CREW CRCW','reduction':'PRAM sum','scan':'PRAM prefix sum'}
        refs=self.search(s['course'],seed_queries.get(concept,concept),10)
        spec['sources']=[r['id'] for r in refs if not r['solution']][:3]
        if spec.get('authentic'):
            rows=self.db.execute("SELECT * FROM passages WHERE course=? AND kind='pdf' AND solution=0 AND reserved=0 AND title LIKE '%1st-part%' AND text LIKE '%EREW%' ORDER BY title DESC",(s['course'],)).fetchall()
            for r in rows:
                question=re.search(r'(?:A\.|A\))\s*(What is the difference between EREW[\s\S]*?)(?=_{3,}|\n\s*B\.)',r['text'])
                if question:
                    spec['prompt']=question[1].strip()
                    spec['sources']=[r['id']]
                    spec['authentic']=True
                    break
            else:
                spec['authentic']=False
        self._activity(sid,spec)

    def next(self,sid):
        if self.beginner_context(sid):return self.advance_beginner(sid)
        session=self.session(sid)
        if session['mode']=='exam':
            raise ValueError('Consegna la simulazione prima di continuare.')
        advance=1
        if session['stage']==0:
            latest=self.db.execute('SELECT grade,aids FROM attempts WHERE session=? ORDER BY rowid DESC LIMIT 1',(sid,)).fetchone()
            if latest and json.loads(latest['grade']).get('correct') is True and not latest['aids']:
                advance=2
        with self.db:
            self.db.execute('UPDATE sessions SET stage=stage+?,updated=? WHERE id=?',(advance,now(),sid))
        self.seed(sid)
        return self.view(sid)

    def recall(self,sid,concept):
        session=self.session(sid)
        if session['mode']=='exam':
            raise ValueError('Termina prima la simulazione.')
        if concept not in CONCEPTS:
            raise ValueError('Competenza non disponibile.')
        refs=self.search(session['course'],concept,4)
        count=self.db.execute('SELECT count(*) FROM attempts WHERE session=? AND concept=?',(sid,concept)).fetchone()[0]
        if concept=='reduction':
            n=32 if count%2==0 else 64
            p=4
            answer=sum(math.ceil((n//2**i)/p) for i in range(1,int(math.log2(n))+1))
            spec={'kind':'numeric','title':'Richiamo · un caso nuovo','prompt':'Senza consultare il laboratorio: riduzione ad albero di %s valori con %s processori, una somma per passo e barriera tra livelli. Quanti passi servono? Non contare copie o comunicazione.'%(n,p),'answer':answer,'solution':'Somma i tempi di ogni livello, arrotondando in alto il numero di somme diviso per i processori.'}
        elif concept=='pram':
            spec={'kind':'choice','title':'Richiamo · accessi concorrenti','prompt':'Più processori scrivono contemporaneamente lo stesso valore nella stessa cella. Quale modello lo ammette con regola common?','options':['EREW','CREW','CRCW'],'answer':'CRCW','solution':'CRCW con regola common: sono consentite scritture concorrenti solo se i valori scritti coincidono.'}
        elif concept=='scan':
            spec={'kind':'numeric','title':'Richiamo · prefix sum','prompt':'Prefix sum inclusivo di [3, 1, 4, 2]. Quanto vale il risultato in posizione 2, contando le posizioni da zero?','answer':8,'solution':'La posizione 2 contiene 3+1+4=8. Il vettore completo è [3,4,8,10].'}
        else:
            spec={'kind':'open','title':'Richiamo · '+CONCEPTS[concept][0],'prompt':'Senza consultare le fonti, spiega '+CONCEPTS[concept][0]+': ipotesi, esempio e un caso limite.','rubric':'Criteri proposti: correttezza, ipotesi, esempio coerente e limiti.'}
        spec.update(concept=concept,sources=[r['id'] for r in refs if not r['solution']][:2])
        self._activity(sid,spec)
        return self.view(sid)

    def view(self,sid):
        session=self.session(sid)
        if session['current'] and '@' in session['current']:
            session['current'],selected=session['current'].rsplit('@',1)
            session['current_version']=int(selected)
        rows=self.db.execute('SELECT * FROM activities WHERE session=? ORDER BY created',(sid,)).fetchall()
        activities=[]
        for r in rows:
            spec=json.loads(r['spec'])
            # Answer keys and full solutions never appear in ordinary browser activity payloads.
            public={k:v for k,v in spec.items() if k not in ('answer','solution','hints','verification')}
            activities.append({'id':r['id'],'version':r['version'],'spec':public,'state':json.loads(r['state']),'created':r['created']})
        messages=[dict(r) for r in self.db.execute('SELECT * FROM messages WHERE session=? ORDER BY rowid',(sid,))]
        attempts=[dict(r,answer=json.loads(r['answer']),grade=json.loads(r['grade'])) for r in self.db.execute('SELECT * FROM attempts WHERE session=? ORDER BY rowid',(sid,))]
        return self.course_learning_view(sid,{'curriculum':self.course_context_public(sid),'learning':self.beginner_context(sid),'session':session,'activities':activities,'messages':messages,'attempts':attempts,'progress':self.progress(session['course']),'recommendation':self.recommendation(session['course'])})

    def activity(self,sid,aid,version):
        row=self.db.execute('SELECT * FROM activities WHERE id=? AND version=? AND session=?',(aid,int(version),sid)).fetchone()
        if not row:
            raise ValueError('Attività non trovata.')
        activity=dict(row,spec=json.loads(row['spec']),state=json.loads(row['state']))
        activity['state']=self._course_inherited_state(sid,activity)
        return activity

    def event(self,sid,aid,version,event_id,kind,payload):
        if kind not in ('change','try','submit','hint','explain','solution','reset'):
            raise ValueError('Evento non ammesso.')
        if len(encoded(payload))>50000:
            raise ValueError('Risposta troppo grande.')
        activity=self.activity(sid,aid,version)
        session=self.session(sid)
        if (session['mode']=='exam' or activity['spec'].get('curriculum',{}).get('recall')) and kind in ('hint','explain','solution'):
            raise ValueError('Gli aiuti sono disponibili dopo la consegna.')
        previous=self.db.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
        if previous:
            if (previous['session'],previous['activity'],previous['version'],previous['kind'],previous['payload']) != (sid,aid,int(version),kind,encoded(payload)):
                raise ValueError('Identità evento già usata con dati diversi.')
            attempt=self.db.execute('SELECT * FROM attempts WHERE event=?',(event_id,)).fetchone()
            return {'duplicate':True,'attempt':dict(attempt,grade=json.loads(attempt['grade'])) if attempt else None}
        response={}
        with self.db:
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)',(event_id,sid,aid,version,kind,encoded(payload),now()))
            if kind in ('change','try','reset'):
                state={} if kind=='reset' else dict(activity['state'],**payload)
                self.db.execute('UPDATE activities SET state=? WHERE id=? AND version=?',(encoded(state),aid,version))
            if kind in ('hint','explain','solution'):
                spec=activity['spec']
                hints=spec.get('hints',['Rileggi le ipotesi e separa letture, scritture e operazioni.'])
                count=self.course_learning_aids(sid,activity,hint_only=True)
                text=(hints[min(count-1,len(hints)-1)] if kind=='hint' else spec.get('solution','Chiedi al tutor una spiegazione usando le fonti collegate.'))
                response['feedback']=text
            if kind=='submit':
                if 'answer' in payload:
                    self.db.execute('UPDATE activities SET state=? WHERE id=? AND version=?',(encoded(dict(activity['state'],answer=payload['answer'])),aid,version))
                aids=self.course_learning_aids(sid,activity)
                grade=self.grade(activity['spec'],payload.get('answer'))
                attempt_id=uid()
                self.db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?,?)',(attempt_id,event_id,sid,aid,version,activity['spec'].get('concept','general'),encoded(payload.get('answer')),encoded(grade),aids,now(),None))
                response['attempt']={'id':attempt_id,'grade':grade,'aids':aids,'concept':activity['spec'].get('concept','general')}
            self.db.execute('UPDATE sessions SET updated=? WHERE id=?',(now(),sid))
            self.course_record_event(sid,aid,version,event_id,kind,response)
        return response

    @staticmethod
    def grade(spec,answer):
        expected=spec.get('answer')
        correct=None
        if expected is not None and spec['kind']=='numeric':
            try:
                correct=math.isclose(float(answer),float(expected),rel_tol=1e-8,abs_tol=1e-8)
            except (ValueError,TypeError):
                correct=False
        elif expected is not None and spec['kind']=='choice':
            correct=str(answer)==str(expected)
        elif expected is not None and spec['kind']=='completion':
            correct=re.sub(r'\s+','',str(answer)).casefold()==re.sub(r'\s+','',str(expected)).casefold()
        return {'correct':correct,'status':'verified' if correct is not None and spec.get('grading_origin','curated')=='curated' else 'provisional','feedback':
                ('Corretto. Ora prova a spiegare perché.' if correct else 'Non ancora. Controlla le ipotesi e riprova.') if correct is not None else 'Risposta salvata. La valutazione aperta richiede il tutor o una tua autovalutazione.',
                'rubric':spec.get('rubric','Correttezza, ipotesi esplicite, ragionamento e casi limite.')}

    def assess(self,sid,attempt_id,grade):
        sid=self.course_attempt_session(sid,attempt_id)
        row=self.db.execute('SELECT * FROM attempts WHERE id=? AND session=?',(attempt_id,sid)).fetchone()
        if not row:
            raise ValueError('Tentativo non trovato.')
        previous=json.loads(row['grade'])
        if previous.get('status')=='verified':
            return previous
        grade=dict(grade,status='provisional',previous=previous)
        with self.db:
            self.db.execute('UPDATE attempts SET grade=? WHERE id=?',(encoded(grade),attempt_id))
        return grade

    def assessment(self,sid,attempt_id):
        sid=self.course_attempt_session(sid,attempt_id)
        attempt=self.db.execute('SELECT * FROM attempts WHERE id=? AND session=?',(attempt_id,sid)).fetchone()
        if not attempt:
            raise ValueError('Consegna una risposta prima della correzione.')
        activity=self.activity(sid,attempt['activity'],attempt['version'])
        sources=[self.source(ref,allow_reserved=True,allow_solutions=True) for ref in activity['spec'].get('sources',[])]
        course=self.session(sid)['course']
        solution_titles={s['title'][:-4]+'.sol.pdf' for s in sources if s['kind']=='pdf' and not s['solution']}
        for title in solution_titles:
            for row in self.db.execute('SELECT id FROM passages WHERE course=? AND title=? AND solution=1 ORDER BY page',(course,title)):
                if row['id'] not in {s['id'] for s in sources}:
                    sources.append(self.source(row['id'],allow_reserved=True,allow_solutions=True))
        return {'attempt':dict(attempt,answer=json.loads(attempt['answer']),grade=json.loads(attempt['grade'])),'activity':activity,'sources':sources}

    def correct(self,sid,attempt_id,text):
        sid=self.course_attempt_session(sid,attempt_id)
        if not str(text).strip():
            raise ValueError('Descrivi la correzione.')
        with self.db:
            result=self.db.execute('UPDATE attempts SET correction=? WHERE id=? AND session=?',(str(text)[:5000],attempt_id,sid))
            if not result.rowcount:
                raise ValueError('Tentativo non trovato.')
        return {'saved':True}

    def review(self,course,concept,card=None,attempt_id=None):
        rid=key(course+':'+concept)
        if card is not None:
            attempt=self.db.execute('SELECT * FROM attempts WHERE id=?',(attempt_id,)).fetchone()
            if not attempt or self.session(attempt['session'])['course']!=course or attempt['concept']!=concept or json.loads(attempt['grade']).get('status')!='verified':
                raise ValueError('Solo tentativi verificati aggiornano il richiamo automatico.')
            old=self.db.execute('SELECT * FROM reviews WHERE id=?',(rid,)).fetchone()
            if old and old['last_attempt']==attempt_id:
                return dict(old)
            with self.db:
                self.db.execute('INSERT OR REPLACE INTO reviews VALUES(?,?,?,?,?,?)',(rid,course,concept,card['due'],encoded(card),attempt_id))
        row=self.db.execute('SELECT * FROM reviews WHERE id=?',(rid,)).fetchone()
        return dict(row,card=json.loads(row['card'])) if row else None

    def progress(self,course):
        attempts=self.db.execute('SELECT a.* FROM attempts a JOIN sessions s ON s.id=a.session WHERE s.course=? ORDER BY a.created',(course,)).fetchall()
        output=[]
        has_pram=self.db.execute("SELECT 1 FROM passages WHERE course=? AND text LIKE '%PRAM%' LIMIT 1",(course,)).fetchone()
        concepts=dict(CONCEPTS) if has_pram else {}
        for attempt in attempts:
            if attempt['concept'] not in concepts:
                activity=self.activity(attempt['session'],attempt['activity'],attempt['version'])
                concepts[attempt['concept']]=(activity['spec'].get('title',attempt['concept']),[],[])
        for concept,(label,_,prerequisites) in concepts.items():
            own=[a for a in attempts if a['concept']==concept]
            successes=[a for a in own if json.loads(a['grade']).get('correct') is True and json.loads(a['grade']).get('status')=='verified' and not a['correction']]
            independent=[a for a in successes if not a['aids']]
            state='da affrontare' if not own else 'affrontato'
            if successes: state='riuscito con aiuti'
            if independent: state='riuscito autonomamente'
            if len(independent)>1 and len({a['activity'] for a in independent})>1 and datetime.fromisoformat(independent[-1]['created'])-datetime.fromisoformat(independent[0]['created'])>=timedelta(days=1):
                state='riconfermato a distanza'
            review=self.review(course,concept)
            output.append({'id':concept,'label':label,'prerequisites':prerequisites,'status':state,'attempts':len(own),'due':review['due'] if review else None})
        return output

    def context(self,sid):
        view=self.view(sid)
        s=view['session']
        events=[dict(r,payload=json.loads(r['payload'])) for r in self.db.execute('SELECT id,kind,payload,activity,version,created FROM events WHERE session=? ORDER BY rowid DESC LIMIT 40',(sid,))]
        return {'curriculum':self.course_context(sid),'learning':self.beginner_context(sid),'session':s,'progress':view['progress'],'recommendation':view['recommendation'],'activity':next((a for a in reversed(view['activities']) if a['id']==s['current'] and (not s.get('current_version') or a['version']==s['current_version'])),None),'attempts':view['attempts'][-12:],'interactions':events}

    def recommendation(self,course):
        progress=self.progress(course)
        due=sorted((p for p in progress if p['due'] and datetime.fromisoformat(p['due'].replace('Z','+00:00'))<=datetime.now(timezone.utc)),key=lambda p:p['due'])
        if due:
            return {'concept':due[0]['id'],'label':due[0]['label'],'reason':'È il momento di verificare se lo ricordi senza aiuti.','action':'recall'}
        rows=self.db.execute('SELECT a.* FROM attempts a JOIN sessions s ON s.id=a.session WHERE s.course=? ORDER BY a.created DESC',(course,)).fetchall()
        for attempt in rows:
            grade=json.loads(attempt['grade'])
            if grade.get('correct') is False and not attempt['correction']:
                label=next((p['label'] for p in progress if p['id']==attempt['concept']),attempt['concept'])
                later_success=any(a['concept']==attempt['concept'] and a['created']>attempt['created'] and json.loads(a['grade']).get('correct') is True for a in rows)
                if not later_success:
                    return {'concept':attempt['concept'],'label':label,'reason':'L’ultimo tentativo ha lasciato un punto da chiarire.','action':'study'}
        for p in progress:
            if p['status'] in ('da affrontare','affrontato','riuscito con aiuti'):
                missing=next((q for q in progress if q['id'] in p['prerequisites'] and q['status'] in ('da affrontare','affrontato')),None)
                candidate=missing or p
                return {'concept':candidate['id'],'label':candidate['label'],'reason':'Consolida il prerequisito prima del prossimo argomento.' if missing else 'Manca ancora una prova autonoma su questo argomento.','action':'study'}
        return {'concept':'general','label':'Un nuovo problema','reason':'Verifica il ragionamento con un problema diverso.','action':'study'}

    def select_activity(self,sid,aid,version):
        self.activity(sid,aid,version)
        with self.db:
            self.db.execute('UPDATE sessions SET current=?,updated=? WHERE id=?',(aid+'@'+str(version),now(),sid))
        return self.view(sid)

    def preferences(self,sid,goal,minutes):
        self.session(sid)
        with self.db:
            self.db.execute('UPDATE sessions SET goal=?,minutes=?,updated=? WHERE id=?',(str(goal)[:200],max(5,min(int(minutes),180)),now(),sid))
        return self.view(sid)

    def resume_session(self, target):
        session=self.session(target)
        self.setting('last_course',session['course'])
        with self.db:self.db.execute('UPDATE sessions SET updated=? WHERE id=?',(now(),target))
        return self.view(target)

    def web_pdf(self, data, page=1):
        import base64
        import pymupdf
        if len(data)>4_000_000:raise ValueError('PDF web troppo grande.')
        with pymupdf.open(stream=base64.b64decode(data,validate=True),filetype='pdf') as doc:
            start=max(0,int(page)-1)
            if start>=len(doc):raise ValueError('Pagina non disponibile.')
            return {'total_pages':len(doc),'first_page':start+1,'text':'\n'.join('PAGE %d\n%s'%(i+1,doc[i].get_text()) for i in range(start,min(start+12,len(doc))))[:24000]}

    def list_materials(self, sid, query='', offset=0, limit=30):
        session=self.session(sid)
        if session['mode']=='exam':
            raise ValueError('Archivio non consultabile durante la simulazione.')
        rows=self.db.execute("""SELECT d.id,d.path,COUNT(p.id) passages,MIN(p.kind) kind
          FROM documents d JOIN passages p ON p.document=d.id
          WHERE d.course=? AND d.issue IS NULL AND p.reserved=0 AND instr(lower(d.path),lower(?))>0
          GROUP BY d.id ORDER BY d.path LIMIT ? OFFSET ?""",
          (session['course'],str(query)[:200],max(1,min(int(limit),50)),max(0,int(offset)))).fetchall()
        return [dict(r) for r in rows]

    def read_material(self, sid, document, start=1, end=80):
        session=self.session(sid)
        if session['mode']=='exam':
            raise ValueError('Archivio non consultabile durante la simulazione.')
        start=max(1,int(start));end=min(max(start,int(end)),start+199)
        rows=self.db.execute("""SELECT p.* FROM passages p JOIN documents d ON d.id=p.document
          WHERE p.document=? AND p.course=? AND d.issue IS NULL AND p.reserved=0
          ORDER BY COALESCE(p.page,0),COALESCE(p.start,0),p.rowid""",(document,session['course'])).fetchall()
        if not rows:
            raise ValueError('Materiale non disponibile nel corso corrente.')
        lines=[];number=0
        for row in rows:
            for text in row['text'].splitlines():
                number+=1
                if start<=number<=end:
                    lines.append({'line':number,'text':text,'source':row['id'],'page':row['page'],'start':row['start'],'quality':row['quality']})
        return {'document':document,'total_lines':number,'lines':lines}

    def grep_materials(self, sid, pattern, document=None, limit=30):
        session=self.session(sid)
        if session['mode']=='exam':
            raise ValueError('Ricerca sospesa durante la simulazione.')
        pattern=str(pattern)[:300]
        if not pattern.strip():
            raise ValueError('Specifica un testo da cercare.')
        rows=self.db.execute("""SELECT p.* FROM passages p JOIN documents d ON d.id=p.document
          WHERE p.course=? AND p.reserved=0 AND d.issue IS NULL AND (? IS NULL OR p.document=?)
          ORDER BY p.document,COALESCE(p.page,0),COALESCE(p.start,0),p.rowid""",(session['course'],document,document))
        output=[];numbers={}
        for row in rows:
            for text in row['text'].splitlines():
                n=numbers.get(row['document'],0)+1;numbers[row['document']]=n
                if pattern.casefold() in text.casefold():
                    output.append({'source':row['id'],'document':row['document'],'path':row['path'],'line':n,'text':text[:1500],'page':row['page'],'start':row['start']})
                    if len(output)>=max(1,min(int(limit),50)):
                        return output
        return output

    def list_sessions(self, course=None, query='', offset=0, limit=30, sid=None):
        if sid and self.session(sid)['mode']=='exam':
            raise ValueError('Storico escluso dal contesto della simulazione.')
        if course:
            self.course_path(course)
        return [dict(r) for r in self.db.execute("""SELECT s.*, (SELECT count(*) FROM messages m WHERE m.session=s.id) messages
          FROM sessions s WHERE (? IS NULL OR s.course=?) AND (instr(lower(s.goal),lower(?))>0 OR EXISTS
          (SELECT 1 FROM messages m WHERE m.session=s.id AND instr(lower(m.text),lower(?))>0))
          ORDER BY s.updated DESC LIMIT ? OFFSET ?""",(course,course,str(query)[:300],str(query)[:300],max(1,min(int(limit),50)),max(0,int(offset))))]

    def read_session(self, sid, target, offset=0, limit=30, activity_offset=0, attempt_offset=0):
        if self.session(sid)['mode']=='exam':
            raise ValueError('Storico escluso dal contesto della simulazione.')
        view=self.view(target)
        if view['session']['mode']=='exam' or any(self.db.execute('SELECT 1 FROM passages WHERE id=? AND reserved=1',(ref,)).fetchone() for a in view['activities'] for ref in a['spec'].get('sources',[])):
            raise ValueError('Questa sessione contiene una prova riservata: non entra nel contesto del tutor.')
        offset=max(0,int(offset));limit=max(1,min(int(limit),50))
        return {'session':view['session'],'messages':view['messages'][offset:offset+limit],
                'total_messages':len(view['messages']),
                'activities':view['activities'][max(0,int(activity_offset)):max(0,int(activity_offset))+10],
                'total_activities':len(view['activities']),
                'attempts':view['attempts'][max(0,int(attempt_offset)):max(0,int(attempt_offset))+20],
                'total_attempts':len(view['attempts'])}

    def embedding_batch(self, course, model, limit=16):
        self.course_path(course)
        # Fingerprints are hashes on disk; compare in Python to avoid a SQLite extension.
        rows=self.db.execute('SELECT p.id,p.text,p.title FROM passages p JOIN documents d ON d.id=p.document WHERE p.course=? AND d.issue IS NULL ORDER BY p.rowid',(course,)).fetchall()
        done={r[0]:r[1] for r in self.db.execute('SELECT source,fingerprint FROM vectors WHERE model=? GROUP BY source',(model,))}
        pending=[dict(r,fingerprint=key(r['text'])) for r in rows if done.get(r['id'])!=key(r['text'])]
        return {'pending':len(pending),'total':len(rows),'items':pending[:max(1,min(int(limit),32))]}

    def save_embeddings(self, model, items):
        if len(items)>32:
            raise ValueError('Batch troppo grande.')
        with self.db:
            for item in items:
                row=self.db.execute('SELECT text FROM passages WHERE id=?',(item['id'],)).fetchone()
                if not row or key(row['text'])!=item['fingerprint']:
                    continue  # Source changed while the worker was computing.
                vectors=item['vectors']
                if not vectors or len(vectors)>1000 or any(len(v)!=384 or not all(math.isfinite(float(x)) for x in v) for v in vectors):
                    raise ValueError('Vettore non valido.')
                self.db.execute('DELETE FROM vectors WHERE source=? AND model=?',(item['id'],model))
                for index,vector in enumerate(vectors):
                    norm=math.sqrt(sum(float(x)**2 for x in vector))
                    if norm==0:raise ValueError('Vettore nullo.')
                    self.db.execute('INSERT INTO vectors VALUES(?,?,?,?,?)',(item['id'],index,model,item['fingerprint'],struct.pack('<384f',*[float(x)/norm for x in vector])))
            self.db.execute('DELETE FROM vectors WHERE source NOT IN (SELECT id FROM passages)')
        return {'saved':len(items)}

    def semantic_search(self, course, query_vector, model, limit=20, mode='learn'):
        self.course_path(course)
        if mode=='exam':
            raise ValueError('Ricerca sospesa durante la simulazione.')
        if len(query_vector)!=384 or not all(math.isfinite(float(x)) for x in query_vector):
            raise ValueError('Vettore non valido.')
        import numpy as np
        rows=self.db.execute("""SELECT v.source,v.vector,v.fingerprint,p.text FROM vectors v JOIN passages p ON p.id=v.source
          JOIN documents d ON d.id=p.document WHERE p.course=? AND p.reserved=0 AND d.issue IS NULL AND v.model=?""",(course,model)).fetchall()
        rows=[r for r in rows if r['fingerprint']==key(r['text'])]
        if not rows:return []
        q=np.asarray(query_vector,dtype=np.float32);q/=max(float(np.linalg.norm(q)),1e-12)
        scores=np.stack([np.frombuffer(r['vector'],dtype='<f4') for r in rows])@q
        best={}
        for row,score in zip(rows,scores):best[row['source']]=max(best.get(row['source'],-1),float(score))
        return [dict(self.source(source),semantic_score=score) for source,score in sorted(best.items(),key=lambda x:x[1],reverse=True)[:max(1,min(int(limit),30))]]

    def dispatch(self,method,args):
        allowed={'preparation_chapter_checkpoint','course_study_time','study_time_mark','study_time_record','study_time_settings','preparation_review_recovery','preparation_optimize_map','preparation_facts','course_peek_task','preparation_model_call','preparation_recover','preparation_usage','preparation_reject','preparation_restart','preparation_scope_followup','preparation_catalog','preparation_begin','preparation_read','preparation_commit','preparation_metric','preparation_decisions','preparation_decide','preparation_evidence','preparation_issue','source_visual','course_coverage','course_scope_material','course_cards','course_note_evidence','course_recalls','course_recall_card','course_create_recall','course_exit_recall','course_focus','course_expose','course_inventory','course_create','course_paths','course_path_view','course_context','course_confirm','course_sync','course_task','course_commit','course_exam_profile','course_status','course_open','course_select','course_position','course_detour','course_journal','course_note','course_correct_note','course_evidence','course_revise','course_undo','course_append','course_simulation','course_unlock','select_beginner_unit','course_lessons','lesson_bundle','beginner_context','set_lesson_plan','select_lesson','advance_beginner','beginner_recall','installation_id','resume_session','web_pdf','list_materials','read_material','grep_materials','list_sessions','read_session','embedding_batch','save_embeddings','semantic_search','bootstrap','import_course','search','source','render_pdf','open_session','view','next','recall','event','message','create_activity','activity','context','assessment','assess','correct','review','setting','select_activity','preferences'}
        if method not in allowed:
            raise ValueError('Metodo non disponibile.')
        return getattr(self,method)(**args)


class Study(PreparationStudy, _StudyBase):
    """Public service: preparation policies wrap every legacy source access."""
    pass


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser()
    parser.add_argument('--root')
    args=parser.parse_args()
    store=Study(data_root(args.root))
    for line in sys.stdin:
        request={}
        try:
            request=json.loads(line)
            result=store.dispatch(request['method'],request.get('args',{}))
            print(encoded({'id':request['id'],'result':result}),flush=True)
        except Exception as exc:
            print(encoded({'id':request.get('id'),'error':str(exc)[:500]}),flush=True)


if __name__=='__main__':
    main()
