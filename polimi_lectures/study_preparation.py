"""Source-grounded preparation v2. Legacy outputs stay archived, never used as evidence."""
from pathlib import Path
import copy
import hashlib
import json
import math
import re
import subprocess
import unicodedata
from collections import Counter
from .study_map import MapStudy,STRATEGY
from .study_course import pack, unpack, stamp, ident, is_exam, exam_type, exam_family, shingles, CHAPTER_LIMITS

VERSION='selective-2.3'
STATUSES={'relevant','prerequisite','outside','uncertain'}

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def question_parts(text):
    """Local conservative segmentation; no held-out question is sent to a model."""
    markers=list(re.finditer(r'(?im)^\s*(?:(?:exercise|question|esercizio|quesito)\s+\d+[^\n]*|(?:\d+|[A-H])[.)]\s+)',text))
    if not markers:return [(0,len(text),text)]
    return [(m.start(),markers[i+1].start() if i+1<len(markers) else len(text),text[m.start():markers[i+1].start() if i+1<len(markers) else len(text)]) for i,m in enumerate(markers)]

def clean_question(text):
    lines=[]
    for line in text.splitlines():
        if re.search(r'(?i)parallel computing|student.*(?:name|id)|surname|politecnico|prof\.|academic year|\b(?:january|february|june|july|september|november)\b|_{3,}|^\s*page\s+\d+',line):continue
        line=re.sub(r'(?i)^\s*(?:exercise|question|esercizio|quesito)\s+\d+','',line)
        lines.append(line)
    return re.sub(r'\s+',' ',' '.join(lines)).strip().casefold()

def exam_tokens(text):
    """Ignore layout, not mathematical meaning or program identifiers."""
    text=unicodedata.normalize('NFC',str(text)).replace('\u00ad','')
    text=re.sub(r'(?m)^\s*_{3,}\s*$', '', text)
    text=text.translate(str.maketrans({'ﬀ':'ff','ﬁ':'fi','ﬂ':'fl','ﬃ':'ffi','ﬄ':'ffl','−':'-','–':'-','—':'-','“':'"','”':'"','‘':"'",'’':"'"}))
    return re.findall(r'\w+|[^\w\s]',text)

def exam_contains(text,original):
    needle=exam_tokens(text);haystack=exam_tokens(original)
    return bool(needle) and any(haystack[i:i+len(needle)]==needle for i in range(len(haystack)-len(needle)+1))

class PreparationStudy(MapStudy):
    def setup_preparation(self):
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS prep_runs(path TEXT PRIMARY KEY,version TEXT,phase TEXT,current TEXT,last_checkpoint TEXT,error TEXT,created TEXT,updated TEXT);
        CREATE TABLE IF NOT EXISTS source_aliases(course TEXT,alias TEXT,document TEXT,PRIMARY KEY(course,alias,document));
        CREATE TABLE IF NOT EXISTS source_links(source TEXT,target TEXT,start REAL,end REAL,status TEXT,confidence TEXT,PRIMARY KEY(source,target));
        CREATE TABLE IF NOT EXISTS protected_spans(course TEXT,source TEXT,start INTEGER,end INTEGER,reason TEXT,PRIMARY KEY(source,start,end));
        CREATE TABLE IF NOT EXISTS prep_spans(path TEXT,source TEXT,fingerprint TEXT,status TEXT,reason TEXT,skills TEXT,selected INTEGER DEFAULT 0,done INTEGER DEFAULT 0,cursor INTEGER DEFAULT 0,PRIMARY KEY(path,source));
        CREATE TABLE IF NOT EXISTS prep_claims(path TEXT,id TEXT,data TEXT,task TEXT,PRIMARY KEY(path,id));
        CREATE TABLE IF NOT EXISTS prep_tasks(id TEXT PRIMARY KEY,path TEXT,kind TEXT,input TEXT,state TEXT,result TEXT,error TEXT,attempts INTEGER DEFAULT 0,started TEXT,finished TEXT,metrics TEXT);
        CREATE TABLE IF NOT EXISTS prep_model_calls(id TEXT PRIMARY KEY,path TEXT,task TEXT,model TEXT,role TEXT,data TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS prep_rejections(id TEXT PRIMARY KEY,path TEXT,task TEXT,error TEXT,output TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS prep_external(task TEXT,url TEXT,fingerprint TEXT,excerpt TEXT,PRIMARY KEY(task,url));
        CREATE TABLE IF NOT EXISTS prep_reads(task TEXT,source TEXT,start INTEGER,end INTEGER,fingerprint TEXT,method TEXT,excerpt TEXT,PRIMARY KEY(task,source,start,end,method));
        CREATE TABLE IF NOT EXISTS prep_issues(path TEXT,id TEXT,chapter TEXT,block TEXT,severity TEXT,data TEXT,state TEXT,PRIMARY KEY(path,id));
        CREATE TABLE IF NOT EXISTS prep_drafts(path TEXT,chapter TEXT,revision INTEGER,data TEXT,dependencies TEXT,solve TEXT,discipline TEXT,didactic TEXT,published INTEGER DEFAULT 0,PRIMARY KEY(path,chapter,revision));
        CREATE TABLE IF NOT EXISTS prep_map_cursor(path TEXT PRIMARY KEY,position INTEGER);
        CREATE TABLE IF NOT EXISTS prep_map_reviews(path TEXT,version INTEGER,data TEXT,PRIMARY KEY(path,version));
        CREATE INDEX IF NOT EXISTS prep_tasks_path ON prep_tasks(path,state);
        CREATE INDEX IF NOT EXISTS prep_spans_path ON prep_spans(path,status,done);
        ''')
        if 'cursor' not in {r[1] for r in self.db.execute('PRAGMA table_info(prep_spans)')}:self.db.execute('ALTER TABLE prep_spans ADD COLUMN cursor INTEGER DEFAULT 0')
        if 'excerpt' not in {r[1] for r in self.db.execute('PRAGMA table_info(prep_reads)')}:self.db.execute('ALTER TABLE prep_reads ADD COLUMN excerpt TEXT')
        self._map_setup()
        self.db.commit()

    def _v2(self,path):return self._path(path)['objective'].get('engine')==2

    def course_create(self,course,request,date='',minutes=None,reserved=None,engine=2,map_strategy=STRATEGY):
        result=super().course_create(course,request,date,minutes,reserved)
        if engine==2:
            o=result['objective'];o['engine']=2;o['map_strategy']=map_strategy
            with self.db:
                self.db.execute('UPDATE course_paths SET objective=? WHERE id=?',(pack(o),result['id']))
                self.db.execute('INSERT INTO prep_runs VALUES(?,?,?,?,?,?,?,?)',(result['id'],VERSION,'scope',None,None,None,stamp(),stamp()))
        return self.course_path_view(result['id'])

    def preparation_restart(self,path):
        p=self._path(path)
        if p['status']=='running':raise ValueError('Metti prima in pausa la preparazione.')
        o=dict(p['objective'],archived=True)
        with self.db:self.db.execute('UPDATE course_paths SET objective=?,status=? WHERE id=?',(pack(o),'paused',path))
        # Only the student's raw request, explicit settings and holdout choices survive. No AI summary/cards.
        return self.course_create(p['course'],o['request'],o.get('date',''),o.get('minutes'),o.get('reserved_requested',[]),engine=2)

    def course_confirm(self,path,summary=None,included=None,excluded=None,reserved=None):
        self._reservation_owner=path
        try:return super().course_confirm(path,summary,included,excluded,reserved)
        finally:self._reservation_owner=None

    def preparation_scope_followup(self,path,note):
        p=self._path(path);o=dict(p['objective'])
        if not self._v2(path) or o.get('archived') or o.get('confirmed'):
            raise ValueError('Il chiarimento è disponibile solo prima della conferma del nuovo percorso.')
        if not isinstance(note,str) or not 3<=len(note.strip())<=3000:
            raise ValueError('Specifica un chiarimento fra 3 e 3000 caratteri.')
        o['scope_followups']=[*o.get('scope_followups',[]),note.strip()]
        if len(pack(o['scope_followups']))>12000:raise ValueError('Troppi chiarimenti: sintetizza il perimetro.')
        o['clarification']=None
        with self.db:
            self.db.execute('UPDATE course_paths SET objective=?,status=?,error=NULL,updated=? WHERE id=?',(pack(o),'scope',stamp(),path))
        return self.course_path_view(path)

    def course_scope_material(self,sid,document,start=1,end=100):
        # Scope may inspect historical questions, but uses the same redaction and
        # exposure policy as every other reader. Never bypass protected spans.
        link=self._path_for_session(sid)
        if link and self._v2(link['path']):
            course=self.session(sid)['course']
            row=self.db.execute('SELECT path FROM documents WHERE id=? AND course=?',(document,course)).fetchone()
            if row:
                if exam_family(row['path'])!=row['path']:raise ValueError('Per definire il perimetro leggi i quesiti, non le soluzioni.')
                return self.read_material(sid,document,start,end)
        return super().course_scope_material(sid,document,start,end)

    def course_unlock(self,path,document):
        p=self._path(path);row=self.db.execute('SELECT path FROM documents WHERE id=? AND course=?',(document,p['course'])).fetchone()
        if not row:raise ValueError('Documento non disponibile.')
        family=exam_family(row[0]);keep=[]
        for did in p['objective'].get('reserved_requested',[]):
            candidate=self.db.execute('SELECT path FROM documents WHERE id=?',(did,)).fetchone()
            if candidate and exam_family(candidate[0])!=family:keep.append(did)
        # Only this objective is edited. Reservations belonging to any other active objective survive.
        objective=dict(p['objective'],reserved_requested=keep)
        with self.db:self.db.execute('UPDATE course_paths SET objective=? WHERE id=?',(pack(objective),path))
        self._reservation_owner=path
        try:selected=self._reserve(p['course'],keep)
        finally:self._reservation_owner=None
        objective['reserved']=selected
        objective['reservation_notice']='La prova rimane riservata perché è scelta anche da un altro obiettivo attivo.' if document in selected else None
        with self.db:self.db.execute('UPDATE course_paths SET objective=? WHERE id=?',(pack(objective),path))
        self.course_sync(path)
        return self.course_path_view(path)

    def _reserve(self,course,documents):
        inventory=self.course_inventory(course)['documents'];byid={r['id']:r for r in inventory}
        if not isinstance(documents,list) or any(d not in byid or byid[d]['solution'] for d in documents):raise ValueError('Temi riservati non validi.')
        inherited=[]
        for row in self.db.execute('SELECT id,objective FROM course_paths WHERE course=?',(course,)):
            objective=unpack(row['objective'],{})
            if row['id']!=getattr(self,'_reservation_owner',None) and not objective.get('archived'):inherited.extend(objective.get('reserved_requested',[]))
        documents=list(dict.fromkeys(list(documents)+[d for d in inherited if d in byid]))
        chosen=set(documents);fingerprints={byid[d]['fingerprint'] for d in documents}
        chosen|={r['id'] for r in inventory if r['exam'] and r['fingerprint'] in fingerprints}
        families={exam_family(byid[d]['path']) for d in chosen}
        selected={r['id'] for r in inventory if exam_family(r['path']) in families or r['id'] in chosen}
        held=[]
        for did in chosen:
            for row in self.db.execute('SELECT text FROM passages WHERE document=?',(did,)):
                for _,_,text in question_parts(row[0]):
                    clean=clean_question(text)
                    if len(clean.split())>=4:held.append((clean,shingles(clean)))
        with self.db:
            old={r[0] for r in self.db.execute("SELECT document FROM course_reservations WHERE course=? AND reason='scelto'",(course,))}
            self.db.execute('INSERT OR IGNORE INTO course_reservation_policy VALUES(?)',(course,))
            self.db.execute('DELETE FROM course_reservations WHERE course=?',(course,))
            self.db.execute('DELETE FROM protected_spans WHERE course=?',(course,))
            self.db.execute('UPDATE passages SET reserved=0 WHERE course=?',(course,))
            for did in selected:
                self.db.execute('INSERT INTO course_reservations VALUES(?,?,?,?)',(course,did,int(byid[did]['exposed']),'scelto' if did in documents else 'soluzione o copia esatta'))
                self.db.execute('UPDATE passages SET reserved=1 WHERE document=?',(did,))
            # Removing a false-positive automatic reservation is not evidence of student exposure.
            for did in old-set(documents):self.db.execute('INSERT OR IGNORE INTO course_exposure VALUES(?,?,?)',(course,did,stamp()))
            for r in inventory:
                if r['id'] in selected or not (r['exam'] or r['solution']):continue
                for source in self.db.execute('SELECT id,text FROM passages WHERE document=?',(r['id'],)).fetchall():
                    for start,end,text in question_parts(source['text']):
                        clean=clean_question(text);parts=shingles(clean)
                        if len(clean.split())<4:continue
                        overlap=any(clean==other or (len(parts)>=15 and len(otherparts)>=15 and len(parts&otherparts)/max(1,len(parts|otherparts))>=.9) for other,otherparts in held)
                        if overlap:self.db.execute('INSERT OR IGNORE INTO protected_spans VALUES(?,?,?,?,?)',(course,source['id'],start,end,'quesito sovrapposto a una prova riservata'))
            # Without reliable question/answer correspondence, keep that answer sheet fully hidden.
            partial_families={exam_family(r[0]) for r in self.db.execute('SELECT DISTINCT d.path FROM protected_spans x JOIN passages p ON p.id=x.source JOIN documents d ON d.id=p.document WHERE x.course=?',(course,))}
            for r in inventory:
                if r['solution'] and exam_family(r['path']) in partial_families:self.db.execute('UPDATE passages SET reserved=1 WHERE document=?',(r['id'],))
        return sorted(selected)

    def source(self,source_id,allow_reserved=False,allow_solutions=True):
        result=super().source(source_id,allow_reserved,allow_solutions)
        # Adjacent context must obey exactly the same access policy as the requested source.
        neighbours=result.get('context',[]);result['context']=[]
        for neighbour in neighbours:
            policy=self.db.execute('SELECT reserved,solution FROM passages WHERE id=?',(neighbour['id'],)).fetchone()
            if not policy or (policy['reserved'] and not allow_reserved) or (policy['solution'] and not allow_solutions):continue
            text=neighbour['text']
            if not allow_reserved:
                for a,b in self.db.execute('SELECT start,end FROM protected_spans WHERE source=? ORDER BY start DESC',(neighbour['id'],)):text=text[:a]+'[Quesito riservato]'+text[b:]
            result['context'].append(dict(neighbour,text=text))
        spans=self.db.execute('SELECT start,end FROM protected_spans WHERE source=? ORDER BY start',(source_id,)).fetchall()
        if spans and not allow_reserved:
            text=result['text']
            for a,b in reversed(spans):text=text[:a]+'\n[Quesito riservato]\n'+text[b:]
            if not re.sub(r'\[Quesito riservato\]|\W','',text):raise ValueError('Fonte riservata.')
            result['text']=text;result['redacted']=True;result['metadata']={'redacted':True}
        partial=self.db.execute('SELECT 1 FROM protected_spans x JOIN passages p ON p.id=x.source WHERE p.document=? LIMIT 1',(result['document'],)).fetchone()
        result['partial_protection']=bool(partial and not allow_reserved)
        if result['kind']=='alignment':
            alignment=result['metadata'].get('alignment',{});material=alignment.get('material') or alignment.get('notebook') or {}
            result['metadata']={'alignment':{'status':alignment.get('status'),'confidence':alignment.get('confidence'),'material':{k:material[k] for k in ('file','page','cell_index','kind') if k in material}}}
        return result

    def search(self,course,query,limit=8,mode='learn'):
        result=[]
        for row in super().search(course,query,limit,mode):
            try:result.append(self.source(row['id'],allow_solutions=mode!='exam'))
            except ValueError:pass
        return result

    def render_pdf(self,source_id,allow_reserved=False,allow_solutions=True):
        source=self.source(source_id,allow_reserved,allow_solutions)
        if source.get('redacted'):raise ValueError('Pagina con quesiti riservati: disponibile soltanto il testo filtrato.')
        return super().render_pdf(source_id,allow_reserved,allow_solutions)

    def _resolve_document(self,course,document):
        if self.db.execute('SELECT 1 FROM documents WHERE course=? AND id=?',(course,document)).fetchone():return document
        rows=self.db.execute('SELECT DISTINCT document FROM source_aliases WHERE course=? AND alias=?',(course,str(document))).fetchall()
        if len(rows)==1:return rows[0][0]
        raise ValueError('Collegamento materiale assente o ambiguo: cerca il documento nel catalogo.')

    def read_material(self,sid,document,start=1,end=80):
        session=self.session(sid)
        if session['mode']=='exam':raise ValueError('Archivio non consultabile durante la simulazione.')
        document=self._resolve_document(session['course'],document)
        start=max(1,int(start));end=min(max(start,int(end)),start+199)
        lines=[];number=0
        for row in self.db.execute('SELECT id FROM passages WHERE document=? ORDER BY COALESCE(page,0),COALESCE(start,0),rowid',(document,)).fetchall():
            try:source=self.source(row[0])
            except ValueError:continue
            for text in source['text'].splitlines():
                number+=1
                if start<=number<=end:lines.append({'line':number,'text':text,'source':source['id'],'page':source['page'],'start':source['start'],'quality':source['quality']})
        if number==0:raise ValueError('Materiale non disponibile nel corso corrente.')
        return {'document':document,'total_lines':number,'lines':lines}

    def grep_materials(self,sid,pattern,document=None,limit=30):
        session=self.session(sid)
        if session['mode']=='exam':raise ValueError('Archivio non consultabile durante la simulazione.')
        if document:document=self._resolve_document(session['course'],document)
        result=[]
        for d in self.list_materials(sid,limit=50) if not document else [{'id':document}]:
            rows=self.read_material(sid,d['id'],1,200)
            for offset in range(1,rows['total_lines']+1,200):
                batch=rows if offset==1 else self.read_material(sid,d['id'],offset,offset+199)
                for line in batch['lines']:
                    if str(pattern).casefold() in line['text'].casefold():result.append(dict(line,document=d['id']))
                    if len(result)>=max(1,min(int(limit),50)):return result
        return result

    def import_course(self,course):
        result=super().import_course(course)
        self.preparation_catalog(course)
        return result

    def preparation_catalog(self,course):
        docs=[dict(r) for r in self.db.execute('SELECT * FROM documents WHERE course=?',(course,))];by_path={d['path']:d for d in docs}
        with self.db:
            self.db.execute('DELETE FROM source_aliases WHERE course=?',(course,))
            for d in docs:
                rel=d['path'].split('/materiali/',1)[-1]
                for alias in {d['id'],d['path'],rel,Path(d['path']).name,d['fingerprint']}:
                    self.db.execute('INSERT OR IGNORE INTO source_aliases VALUES(?,?,?)',(course,alias,d['id']))
            self.db.execute('DELETE FROM source_links WHERE source IN (SELECT id FROM passages WHERE course=?)',(course,))
            for r in self.db.execute("SELECT id,start,end,metadata FROM passages WHERE course=? AND kind='alignment'",(course,)).fetchall():
                data=unpack(r['metadata'],{}).get('alignment',{});material=data.get('material') or data.get('notebook') or {}
                file=material.get('file');target=by_path.get('corsi/'+course+'/materiali/'+str(file))
                if not target and file:
                    matches=[d for d in docs if Path(d['path']).name==Path(file).name]
                    if len(matches)==1:target=matches[0]
                if not target:continue
                aliases=[material.get('id'),material.get('file_id')]
                if material.get('page_id'):aliases.append(str(material['page_id']).split(':page:',1)[0])
                for alias in aliases:
                    if alias:self.db.execute('INSERT OR IGNORE INTO source_aliases VALUES(?,?,?)',(course,str(alias),target['id']))
                pages=[material['page']] if material.get('page') is not None else [material['cell_index']] if material.get('cell_index') is not None else [cell['cell_index'] for cell in material.get('cells',[]) if cell.get('cell_index') is not None]
                for page in dict.fromkeys(pages):
                    for p in self.db.execute('SELECT id FROM passages WHERE document=? AND page=?',(target['id'],page)).fetchall():
                        self.db.execute('INSERT OR REPLACE INTO source_links VALUES(?,?,?,?,?,?)',(r['id'],p['id'],r['start'],r['end'],data.get('status','candidate'),str(data.get('confidence','candidate'))))
        return {'documents':len(docs),'links':self.db.execute('SELECT count(*) FROM source_links l JOIN passages p ON p.id=l.source WHERE p.course=?',(course,)).fetchone()[0]}

    def course_sync(self,path):
        if not self._v2(path):return super().course_sync(path)
        p=self._path(path)
        if not p['objective'].get('confirmed'):return
        self.preparation_catalog(p['course'])
        inventory=self.course_inventory(p['course'])['documents'];target=exam_type(p['objective']['request'])
        changed=False
        with self.db:
            present=set()
            for d in inventory:
                if d['solution'] or d['issue'] or d['duplicate_of'] or d['administrative']:continue
                for row in self.db.execute("SELECT * FROM passages WHERE document=? AND kind!='alignment' AND reserved=0 ORDER BY COALESCE(page,start,0),rowid",(d['id'],)).fetchall():
                    try:self.source(row['id'],allow_solutions=False)
                    except ValueError:continue
                    present.add(row['id']);old=self.db.execute('SELECT fingerprint,status,reason FROM prep_spans WHERE path=? AND source=?',(path,row['id'])).fetchone()
                    fingerprint=digest([d['fingerprint'],self.source(row['id'],allow_solutions=False)['text']])
                    paper_type=exam_type(d['title'])
                    incompatible=d['exam'] and target and target.startswith('part:') and paper_type and paper_type.startswith('part:') and target!=paper_type
                    if old and old[0]==fingerprint:
                        if d['exam'] and not incompatible and old['status']=='outside' and old['reason']=='Tema di un diverso parziale':
                            self.db.execute("UPDATE prep_spans SET status='relevant',reason='Prova da valutare per singoli quesiti',selected=1,done=0,cursor=0 WHERE path=? AND source=?",(path,row['id']))
                        continue
                    changed|=bool(old)
                    status='outside' if incompatible else ('relevant' if d['exam'] else 'unreviewed')
                    self.db.execute('INSERT OR REPLACE INTO prep_spans VALUES(?,?,?,?,?,?,?,0,0)',(path,row['id'],fingerprint,status,'Tema di un diverso parziale' if incompatible else 'Da valutare',pack([]),int(bool(incompatible or d['exam']))))
            for r in self.db.execute('SELECT source FROM prep_spans WHERE path=?',(path,)).fetchall():
                if r[0] not in present:self.db.execute('DELETE FROM prep_spans WHERE path=? AND source=?',(path,r[0]));changed=True
            if changed:
                # Evidence and drafts carry their own fingerprints; old content is retained as history.
                self.db.execute("UPDATE prep_tasks SET state='stale' WHERE path=? AND state='done'",(path,))
                self.db.execute('DELETE FROM prep_map_reviews WHERE path=?',(path,))
                self.db.execute('DELETE FROM prep_map_cursor WHERE path=?',(path,))
                plan=self._plan(path)
                if plan and plan['data'].get('final'):
                    data=dict(plan['data'],final=False)
                    self.db.execute('INSERT INTO course_plans VALUES(?,?,?,?,?)',(path,plan['version']+1,pack(data),'Fonti cambiate: verifica mirata',stamp()))
        return {'sources':len(present)}

    def _prep_available(self,path,rows,budget):
        selected=[];used=0
        for row in rows:
            source=self.source(row['source'],allow_solutions=False)
            cursor=row['cursor'];full=source['text'];text=full[cursor:];remaining=budget-used
            if remaining<1000 and selected:break
            maximum=max(3000,remaining*3)
            if len(text)>maximum:
                boundary=max(text.rfind('\n\n',maximum//2,maximum),text.rfind('\n',maximum//2,maximum))
                if boundary<0:boundary=text.rfind(' ',maximum//2,maximum)
                stop=cursor+(boundary if boundary>0 else maximum)
            else:stop=len(full)
            piece={k:source[k] for k in ('id','document','page','start','end','kind','title','quality')}
            piece.update(selection_status=row['status'],text=full[cursor:stop],start_char=cursor,end_char=stop,total_characters=len(full),boundary_context={'before':full[max(0,cursor-250):cursor],'after':full[stop:stop+250]})
            selected.append(piece);used+=math.ceil(len(piece['text'])/3)
            if stop<len(full):break
        return selected

    def _prep_task(self,path,data):
        if data.get('kind') in ('chapter','repair_chapter'):data=dict(data,chapter_limits=dict(CHAPTER_LIMITS))
        p=self._path(path);refs=set()
        def gather(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if key in ('source','id') and isinstance(item,str):refs.add(item)
                    if key=='sources' and isinstance(item,list):refs.update(r for r in item if isinstance(r,str))
                    if isinstance(item,(dict,list)):gather(item)
            elif isinstance(value,list):
                for item in value:gather(item)
        gather(data);revisions={}
        for ref in sorted(refs):
            row=self.db.execute('SELECT d.id,d.fingerprint FROM passages p JOIN documents d ON d.id=p.document WHERE p.id=?',(ref,)).fetchone()
            if row:revisions[row['id']]=row['fingerprint']
        data=dict(data,source_revisions=revisions);key=digest([VERSION,p['objective'],data])
        task=dict(data,task_id=key,engine=2,objective=p['objective'])
        if not getattr(self,'_peek_preparation',False):
            with self.db:self.db.execute('INSERT OR IGNORE INTO prep_tasks(id,path,kind,input,state) VALUES(?,?,?,?,?)',(key,path,data['kind'],pack(task),'pending'))
        return task

    def course_peek_task(self,path,input_tokens=32000,model_key=''):
        self._peek_preparation=True
        try:
            task=self.course_task(path,input_tokens,model_key)
            self._peek_cache=(path,int(input_tokens),self.db.total_changes,self.db.execute('PRAGMA data_version').fetchone()[0],copy.deepcopy(task))
            return task
        finally:self._peek_preparation=False

    def course_task(self,path,input_tokens=32000,model_key=''):
        cache=getattr(self,'_peek_cache',None)
        if cache and not getattr(self,'_peek_preparation',False):
            self._peek_cache=None
            same=cache[:4]==(path,int(input_tokens),self.db.total_changes,self.db.execute('PRAGMA data_version').fetchone()[0])
            task=cache[4]
            # A brand-new build needs its manifest persisted by the normal task builder.
            built=not task.get('build') or self.db.execute('SELECT 1 FROM prep_map_builds WHERE path=? AND build=?',(path,task['build'])).fetchone()
            if same and task.get('engine')==2 and task.get('kind')!='done' and built:
                data={k:v for k,v in task.items() if k not in ('task_id','engine','objective')}
                data['model_key']=model_key
                return self._prep_task(path,data)
        p=self._path(path)
        if p['objective'].get('archived'):raise ValueError('Preparazione archiviata: disponibile solo per consultazione.')
        if not self._v2(path) or not p['objective'].get('confirmed'):
            task=super().course_task(path)
            return self._prep_task(path,task) if self._v2(path) else task
        self.course_sync(path);budget=max(1000,min(64000,int(input_tokens)))
        common={'model_key':model_key,'budget':budget}
        rows=self.db.execute('SELECT s.*,d.path document_path,p.kind,p.title FROM prep_spans s JOIN passages p ON p.id=s.source JOIN documents d ON d.id=p.document WHERE s.path=? AND s.done=0 AND s.status!=? ORDER BY d.path,COALESCE(p.page,p.start,0),p.rowid',(path,'outside')).fetchall()
        # Analyse real exam papers before lesson selection. An alignment can never become an exam.
        exams=[r for r in rows if r['kind']=='pdf' and is_exam(r['document_path'])]
        if exams:
            doc=self.source(exams[0]['source'])['document'];group=[r for r in exams if self.source(r['source'])['document']==doc]
            return self._prep_task(path,dict(common,kind='exam_reading',document=doc,sources=self._prep_available(path,group,budget)))
        undecided=[r for r in rows if not r['selected']]
        if undecided:
            doc=self.source(undecided[0]['source'])['document'];group=[r for r in undecided if self.source(r['source'])['document']==doc]
            previews=[]
            # Bounded triage reads complete natural passages where possible, not 80 tiny excerpts.
            # A long page is explicitly truncated and must remain uncertain if context is missing.
            for row in group[:12]:
                source=self.source(row['source'],allow_solutions=False)
                text=source['text'];maximum=max(3000,min(12000,budget*2))
                previews.append({k:source[k] for k in ('id','page','start','end','kind','quality')}|{'preview':text[:maximum],'truncated':len(text)>maximum})
                if len(pack(previews))>budget*2 and len(previews)>1:previews.pop();break
            profile=self.course_exam_profile(path)
            profile={key:profile[key] for key in ('total','excluded_total','formats','skills','sample_size','limitations')}
            history=dict(self.db.execute('SELECT s.status,count(*) FROM prep_spans s JOIN passages p ON p.id=s.source WHERE s.path=? AND p.document=? AND s.selected=1 GROUP BY s.status',(path,doc)).fetchall())
            return self._prep_task(path,dict(common,kind='selection',document=doc,title=self.source(group[0]['source'])['title'],previews=previews,exam_profile=profile,selection_history={'reviewed':sum(history.values()),'outside':history.get('outside',0)}))
        if rows:
            doc=self.source(rows[0]['source'])['document'];group=[r for r in rows if self.source(r['source'])['document']==doc]
            sources=self._prep_available(path,group,budget)
            links=[];folder=str(Path(self.source(rows[0]['source'])['path']).parent.parent)+'/'
            if rows[0]['kind']=='video':
                for link in self.db.execute('SELECT DISTINCT l.* FROM source_links l JOIN passages p ON p.id=l.source WHERE p.path LIKE ? ORDER BY l.start',(folder+'%',)).fetchall():
                    if not any(s['start'] is not None and link['start']<=s['end'] and link['end']>=s['start'] for s in sources):continue
                    try:target=self.source(link['target'],allow_solutions=False)
                    except ValueError:continue
                    prior=self.db.execute('SELECT status,done FROM prep_spans WHERE path=? AND source=?',(path,target['id'])).fetchone()
                    if prior and (prior['done'] or prior['status']=='outside'):continue
                    if target['id'] in {x['id'] for x in sources} or target['id'] in {x['source']['id'] for x in links}:continue
                    if len(pack(sources))+len(pack(links))+len(target['text'])>budget*2.5:break
                    links.append({'source':{k:target[k] for k in ('id','document','text','page','kind','title','quality')},'start':link['start'],'end':link['end'],'status':link['status'],'confidence':link['confidence']})
            return self._prep_task(path,dict(common,kind='evidence_reading',document=doc,sources=sources,links=links))
        claims=self.preparation_evidence(path,limit=100000)
        plan=self._plan(path)
        if not plan or not plan['data'].get('final'):
            if p['objective'].get('map_strategy')==STRATEGY:return self._map_task(path,claims,common)
            cursor=self.db.execute('SELECT position FROM prep_map_cursor WHERE path=?',(path,)).fetchone();offset=cursor[0] if cursor else 0
            batch=[];used=0
            for claim in claims[offset:]:
                cost=math.ceil(len(pack(claim))/3)
                if batch and used+cost>budget//2:break
                batch.append(claim);used+=cost
            selection=[dict(r) for r in self.db.execute('SELECT p.document,s.status,count(*) intervals FROM prep_spans s JOIN passages p ON p.id=s.source WHERE s.path=? GROUP BY p.document,s.status',(path,))]
            return self._prep_task(path,dict(common,kind='map',student_clarifications=[dict(r,data=unpack(r['data'])) for r in self.db.execute("SELECT * FROM prep_issues WHERE path=? AND chapter='map' AND state='needs_review'",(path,))],evidence=batch,evidence_offset=offset,final_batch=offset+len(batch)>=len(claims),exam_profile=self.course_exam_profile(path),selection=selection,previous=plan))
        reviewed=self.db.execute('SELECT data FROM prep_map_reviews WHERE path=? AND version=?',(path,plan['version'])).fetchone()
        if not reviewed:return self._prep_task(path,dict(common,kind='map_review',plan=plan,evidence_context=self._map_context(path,claims),exam_profile=self._map_profile(path)))
        if p['objective'].get('map_strategy')==STRATEGY and any(i.get('severity')=='blocking' for i in unpack(reviewed['data']).get('issues',[])):
            return self._map_task(path,claims,common)
        position=self.db.execute('SELECT * FROM course_path_sessions WHERE path=? ORDER BY rowid DESC LIMIT 1',(path,)).fetchone();chapters=plan['data']['chapters'];index=next((i for i,c in enumerate(chapters) if position and c['id']==position['chapter']),0)
        for chapter in chapters[index:index+2]:
            old=self._chapter(path,chapter['id']);draft=self.db.execute('SELECT * FROM prep_drafts WHERE path=? AND chapter=? ORDER BY revision DESC LIMIT 1',(path,chapter['id'])).fetchone()
            notes=[dict(r,data=unpack(r['data'])) for r in self.db.execute("SELECT * FROM prep_issues WHERE path=? AND chapter=? AND state='needs_review'",(path,chapter['id']))]
            if notes and draft:
                return self._prep_task(path,dict(common,kind='repair_chapter',chapter=chapter,draft_revision=draft['revision'],draft=unpack(draft['data']),reviews={key:unpack(draft[key],{}) for key in ('solve','discipline','didactic')},student_clarifications=notes))
            dependency=digest([plan,self._preference_fingerprint(p['course'])])
            if draft and draft['dependencies']!=dependency and not draft['published']:
                with self.db:self.db.execute('UPDATE prep_drafts SET published=2 WHERE path=? AND chapter=? AND revision=?',(path,chapter['id'],draft['revision']))
                draft=None
            if old and not self._chapter_stale(old) and (not draft or draft['published']):continue
            if not draft or draft['published']:
                return self._prep_task(path,dict(common,kind='chapter',chapter=chapter,plan=plan,evidence_context=self._map_context(path,claims,chapter),profile=self.course_exam_profile(path),sources=[self.source(ref,allow_solutions=False) for ref in chapter['sources'][:8]],preferences=self.course_journal(p['course'],kind='preference',limit=12)))
            content=unpack(draft['data']);reviews={key:unpack(draft[key]) for key in ('solve','discipline','didactic')}
            refs=list(dict.fromkeys(ref for b in content['blocks'] for ref in b.get('sources',b.get('spec',{}).get('sources',[]))))
            originals=[];used=len(pack(content))//3
            for ref in refs:
                source=self.source(ref,allow_solutions=False)
                if used+len(source['text'])//3>budget:break
                originals.append({k:source[k] for k in ('id','document','text','page','start','end','quality','kind')});used+=len(source['text'])//3
            taskbase=dict(common,chapter=chapter,draft_revision=draft['revision'],draft=content,originals=originals,profile=self.course_exam_profile(path),reviews=reviews)
            if not draft['solve']:
                blind=copy.deepcopy(content)
                for block in blind['blocks']:
                    if block['kind']=='activity':
                        allowed={'kind','title','prompt','options','sources','origin','assumptions','model','html','fallback'}
                        block['spec']={k:v for k,v in block['spec'].items() if k in allowed}
                taskbase['draft']=blind;taskbase.pop('reviews');return self._prep_task(path,dict(taskbase,kind='review_solve'))
            if not draft['discipline']:return self._prep_task(path,dict(taskbase,kind='review_discipline'))
            if not draft['didactic']:return self._prep_task(path,dict(taskbase,kind='review_didactic'))
            blocking=[i for review in (reviews['discipline'],reviews['didactic']) for i in review.get('issues',[]) if i['severity']=='blocking']
            if blocking and draft['revision']<3:return self._prep_task(path,dict(taskbase,kind='repair_chapter'))
            return self._prep_task(path,dict(taskbase,kind='publish'))
        return {'kind':'done','engine':2}

    def preparation_begin(self,path,task):
        p=self._path(path)
        row=self.db.execute('SELECT input,state,metrics FROM prep_tasks WHERE id=? AND path=?',(task['task_id'],path)).fetchone()
        if not row or unpack(row['input'])!=task:raise ValueError('Compito non valido.')
        with self.db:
            self.db.execute("UPDATE prep_tasks SET state='running',started=?,attempts=attempts+1 WHERE id=?",(stamp(),task['task_id']))
            self.db.execute('UPDATE prep_runs SET version=?,phase=?,current=?,error=NULL,updated=? WHERE path=?',(VERSION,task['kind'],task['task_id'],stamp(),path))
        def register(source):
            if isinstance(source,dict) and source.get('id') and 'text' in source:
                self.preparation_read(task['task_id'],source,'input')
            if isinstance(source,dict):
                for v in source.values():register(v)
            elif isinstance(source,list):
                for v in source:register(v)
        register(task)
        return {'started':True,'metrics':unpack(row['metrics'],{}),'review_recovery':self._review_recovery(path,task)}

    def _review_recovery(self,path,task):
        """Reuse a rejected review of this exact immutable task, never an unchecked approval."""
        if task['kind'] not in ('review_discipline','review_didactic'):return None
        draft=task['draft'];blocks={b['id'] for b in draft['blocks']}
        refs={ref for b in draft['blocks'] for ref in b.get('sources',b.get('spec',{}).get('sources',[]))}
        best=None;score=(-1,-1)
        for row in self.db.execute('SELECT output,error FROM prep_rejections WHERE path=? AND task=? ORDER BY rowid DESC LIMIT 6',(path,task['task_id'])):
            if not row['error'].startswith(('La revisione deve','Citazione non letta')):continue
            try:
                result=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',row['output'].strip()))
                if not isinstance(result,dict) or not result.get('summary') or not isinstance(result.get('issues'),list):continue
                checked=result.get('checked_sources',[]);checked_blocks=result.get('checked_blocks',[])
                if not isinstance(checked,list) or not isinstance(checked_blocks,list) or any(not isinstance(s,str) for s in checked+checked_blocks):continue
                candidate=(int(set(checked_blocks)==blocks),len(refs&set(checked)))
                if candidate<=score:continue
                try:self._review_result(path,task,result,draft);error=''
                except ValueError as invalid:error=str(invalid)
                best={'result':result,'error':error};score=candidate
            except (ValueError,TypeError,KeyError):continue
        if best is not None:best['read_sources']=[r[0] for r in self.db.execute('SELECT DISTINCT source FROM prep_reads WHERE task=? ORDER BY source',(task['task_id'],))]
        return best

    def preparation_review_recovery(self,path,task):
        row=self.db.execute('SELECT input FROM prep_tasks WHERE path=? AND id=?',(path,task)).fetchone()
        if not row:raise ValueError('Compito non trovato nel percorso.')
        return self._review_recovery(path,unpack(row['input'])) or {'read_sources':[r[0] for r in self.db.execute('SELECT DISTINCT source FROM prep_reads WHERE task=? ORDER BY source',(task,))]}

    def preparation_read(self,task,result,method='tool'):
        row=self.db.execute('SELECT path,state FROM prep_tasks WHERE id=?',(task,)).fetchone()
        if not row or row['state'] not in ('running','waiting','correcting'):raise ValueError('Lettura senza compito attivo.')
        p=self._path(row['path']);items=[]
        if method=='read_web_page':
            url=result.get('url');text=result.get('text','')
            if not isinstance(url,str) or not url.startswith('https://') or not text:raise ValueError('Fonte esterna senza URL o testo letto.')
            with self.db:self.db.execute('INSERT OR REPLACE INTO prep_external VALUES(?,?,?,?)',(task,url,digest(text),text))
            return {'recorded':1}
        def collect(value):
            if isinstance(value,list):
                for v in value:collect(v)
            elif isinstance(value,dict):
                source_id=value.get('source') if isinstance(value.get('source'),str) else value.get('id')
                if source_id and (method=='input' or 'text' in value or 'lines' in value):items.append((source_id,value.get('line'),value.get('start_char'),value.get('end_char'),value.get('text','')))
                for v in value.values():
                    if isinstance(v,(dict,list)):collect(v)
        collect(result)
        with self.db:
            for ref,line,first,last,excerpt in items:
                try:source=self.source(ref,allow_solutions=False)
                except ValueError:continue
                if source['course']!=p['course']:raise ValueError('Lettura di un altro corso.')
                fingerprint=self.db.execute('SELECT fingerprint FROM documents WHERE id=?',(source['document'],)).fetchone()[0]
                self.db.execute('INSERT OR IGNORE INTO prep_reads VALUES(?,?,?,?,?,?,?)',(task,ref,int(first if first is not None else line or 0),int(last if last is not None else line or len(source['text'])),fingerprint,method,excerpt))
        return {'recorded':len(items)}

    def _prep_refs(self,path,task,refs):
        refs=self._refs(self._path(path)['course'],refs)
        allowed={r[0] for r in self.db.execute('SELECT source FROM prep_reads WHERE task=?',(task['task_id'],))}
        unread=set(refs)-allowed
        if unread:raise ValueError('Citazione non letta nel compito: '+pack(sorted(unread))+'. Usa read_source o read_material prima di citarla; non inventare una lettura.')
        return refs

    def preparation_commit(self,path,task,result):
        record=self.db.execute('SELECT * FROM prep_tasks WHERE id=? AND path=?',(task.get('task_id'),path)).fetchone()
        if not record or unpack(record['input'])!=task:raise ValueError('Compito non valido.')
        if record['state']=='done':
            if unpack(record['result'])!=result:raise ValueError('Checkpoint già completato: risultato differente rifiutato.')
            return self.course_path_view(path)
        if record['state'] not in ('running','waiting','correcting'):raise ValueError('Compito non attivo.')
        raw_result=copy.deepcopy(result)
        kind=task['kind'];p=self._path(path)
        # Each referenced document must still match the revision actually read.
        for r in self.db.execute('SELECT r.fingerprint,d.fingerprint current FROM prep_reads r JOIN passages s ON s.id=r.source JOIN documents d ON d.id=s.document WHERE r.task=?',(task['task_id'],)):
            if r['fingerprint']!=r['current']:raise ValueError('Fonte cambiata durante il compito: riprendi la preparazione aggiornata.')
        if kind=='scope':
            legacy=dict(task);[legacy.pop(k,None) for k in ('task_id','engine')]
            super().course_commit(path,legacy,result)
        elif kind=='selection':
            decisions=result.get('decisions',[]);expected={r['id'] for r in task['previews']}
            if len(decisions)!=len(expected) or {d.get('source') for d in decisions}!=expected:raise ValueError('Valuta tutti e soli gli intervalli proposti.')
            if any(d.get('status') not in STATUSES or not d.get('reason') for d in decisions):raise ValueError('Selezione senza stato o motivazione.')
            with self.db:
                for d in decisions:self.db.execute('UPDATE prep_spans SET status=?,reason=?,skills=?,selected=1 WHERE path=? AND source=?',(d['status'],d['reason'],pack(d.get('skills',[])),path,d['source']))
        elif kind in ('exam_reading','evidence_reading'):
            evidence=result.get('evidence',[])
            if not isinstance(evidence,list) or not evidence:raise ValueError('Servono evidenze nuove oppure una lacuna esplicita in evidence.')
            if len(pack(result))>100000:raise ValueError('Evidenze troppo lunghe: sintetizza i singoli fatti, non copiare la fonte.')
            validated=[]
            for e in evidence:
                if not e.get('concept') or not e.get('statement'):raise ValueError('Evidenza senza concetto o affermazione.')
                provenance=e.get('provenance','course')
                if provenance not in ('course','general','external'):raise ValueError('Provenienza del fatto non valida.')
                if provenance=='external':
                    urls=e.get('external_sources',[])
                    if not urls or not e.get('notation_comparison'):raise ValueError('La fonte esterna richiede URL letti e confronto con la notazione del corso.')
                    if any(not self.db.execute('SELECT 1 FROM prep_external WHERE task=? AND url=?',(task['task_id'],url)).fetchone() for url in urls):raise ValueError('Fonte web non letta tramite gli strumenti.')
                refs=self._prep_refs(path,task,e.get('sources'));validated.append(dict(e,sources=refs,read_ranges=[dict(r) for r in self.db.execute('SELECT source,start,end,method FROM prep_reads WHERE task=?',(task['task_id'],)) if r['source'] in refs]))
            questions=result.get('questions',[])
            if not isinstance(questions,list):raise ValueError('questions deve essere una lista di quesiti.')
            def validate_question(question_index,q):
                if not isinstance(q,dict) or not isinstance(q.get('text'),str):raise ValueError('Quesito senza testo originale valido.')
                label=f"questions[{question_index}]"
                refs=self._prep_refs(path,task,q.get('sources'))
                if not q.get('text') or q.get('format') not in ('choice','numeric','open','code','mixed','unknown') or not isinstance(q.get('in_scope'),bool) or not q.get('skills'):raise ValueError('Quesito incompleto.')
                origin='exam' if kind=='exam_reading' else q.get('origin','generated')
                if kind=='exam_reading' and any(self.source(ref)['document']!=task['document'] for ref in refs):raise ValueError(f'{label}: il quesito deve citare soltanto pagine della prova originale {task["document"]}. Fonti ricevute: {refs}.')
                if origin=='exam' and kind!='exam_reading':raise ValueError('Una domanda didattica non può alimentare il profilo d’esame.')
                if q['format']=='choice' and (not isinstance(q.get('options'),list) or len(q['options'])<2):raise ValueError('Formato a scelta non attestato: conserva unknown/open senza inventare opzioni.')
                if kind=='exam_reading':
                    # Validate each citation independently. Never borrow words from unrelated
                    # pages or join disjoint tool reads into a fictitious contiguous quotation.
                    originals=[]
                    for ref in refs:
                        receipts=self.db.execute('SELECT excerpt,start,end,method FROM prep_reads WHERE task=? AND source=? ORDER BY method,start,end',(task['task_id'],ref)).fetchall()
                        originals.extend(r['excerpt'] or '' for r in receipts)
                        lines=list({r['start']:r for r in receipts if r['method'] in ('read_material','read_scope_material') and r['start']==r['end']}.values())
                        group=[];previous=None
                        for receipt in sorted(lines,key=lambda r:r['start']):
                            if previous is not None and receipt['start']!=previous+1:
                                if group:originals.append('\n'.join(group))
                                group=[]
                            group.append(receipt['excerpt'] or '');previous=receipt['start']
                        if group:originals.append('\n'.join(group))
                    if not any(exam_contains(q['text'],original) for original in originals):
                        raise ValueError(f'{label}: testo non attestato nelle pagine citate {refs}: {q["text"][:180]!r}. Copia un singolo quesito/sottopunto contiguo, con codice, formule e opzioni originali; non unire domande distinte. Le righe vuote per le risposte sono ignorate.')
                    for option in q.get('options',[]):
                        if not any(exam_contains(str(option),original) for original in originals):raise ValueError(f'{label}: opzione non presente nelle pagine citate.')
                q.update(origin=origin,authenticity_verified=kind=='exam_reading',sources=refs,family=digest([re.sub(r'\d+','#',clean_question(q['text'])),q['format']])[:24])
            question_errors=[]
            for question_index,q in enumerate(questions):
                try:validate_question(question_index,q)
                except ValueError as error:question_errors.append(f'questions[{question_index}]: {error}')
            if question_errors:raise ValueError('\n'.join(question_errors))
            with self.db:
                for e in validated:
                    cid=digest([e['concept'],e['statement'],e['sources']])[:24]
                    dependencies={self.source(ref)['document']:self.db.execute('SELECT fingerprint FROM documents WHERE id=?',(self.source(ref)['document'],)).fetchone()[0] for ref in e['sources']}
                    self.db.execute('INSERT OR REPLACE INTO prep_claims VALUES(?,?,?,?)',(path,cid,pack(dict(e,id=cid,dependencies=dependencies,access_fingerprints={ref:digest(self.source(ref,allow_solutions=False)['text']) for ref in e['sources']})),task['task_id']))
                for q in questions:
                    qid=digest(clean_question(q['text']))[:24];existing=self.db.execute('SELECT data FROM course_questions WHERE path=? AND id=?',(path,qid)).fetchone()
                    occurrences=unpack(existing[0]).get('occurrences',[]) if existing else []
                    occurrence={'document':task['document'],'sources':q['sources']}
                    if occurrence not in occurrences:occurrences.append(occurrence)
                    q['occurrences']=occurrences
                    self.db.execute('INSERT OR REPLACE INTO course_questions VALUES(?,?,?,?)',(path,qid,task['document'],pack(q)))
                for s in task['sources']:self.db.execute('UPDATE prep_spans SET done=?,cursor=? WHERE path=? AND source=?',(int(s.get('end_char',len(s['text']))>=s.get('total_characters',len(s['text']))),s.get('end_char',len(s['text'])),path,s['id']))
                for link in task.get('links',[]):
                    ref=link['source']['id'];self.db.execute("UPDATE prep_spans SET done=1,cursor=? WHERE path=? AND source=? AND selected=1 AND status!='outside'",(len(link['source']['text']),path,ref))
                if kind=='exam_reading':self.db.execute('INSERT OR IGNORE INTO course_exposure VALUES(?,?,?)',(p['course'],task['document'],stamp()))
        elif kind in ('map_outline','map_contribution'):
            self._map_commit_part(path,task,result)
        elif kind=='map':
            if task.get('strategy')==STRATEGY:result=self._map_merge(path,task,result)
            previous=self._plan(path);data=self._validate_plan(path,result,previous,bibliography_budget=task.get('strategy')==STRATEGY)
            included=p['objective']['included'];coverage=result.get('objective_coverage',[])
            if task.get('final_batch') and {c.get('index') for c in coverage}!=set(range(len(included))):raise ValueError('Collega tutti gli obiettivi ai capitoli o a lacune esplicite.')
            ids={c['id'] for c in data['chapters']}
            if any(not c.get('chapters') and not c.get('gap') or not set(c.get('chapters',[]))<=ids for c in coverage):raise ValueError('Copertura degli obiettivi non valida.')
            selected={r[0] for r in self.db.execute("SELECT DISTINCT p.document FROM prep_spans s JOIN passages p ON p.id=s.source WHERE s.path=? AND s.status!='outside'",(path,))}
            mapped={d for c in data['chapters'] for d in c.get('coverage',[])}
            if task.get('final_batch') and not selected<=mapped:raise ValueError('La mappa omette fonti selezionate: '+', '.join(selected-mapped))
            with self.db:
                if task.get('repair_version'):self._map_commit_scope_repairs(path,task,raw_result)
                self.db.execute('INSERT INTO course_plans VALUES(?,?,?,?,?)',(path,previous['version']+1 if previous else 1,pack(dict(data,final=bool(task.get('final_batch')))),'Correzione mirata dopo revisione' if task.get('repair_version') else 'Mappa delle evidenze selezionate',stamp()))
            with self.db:self.db.execute('INSERT OR REPLACE INTO prep_map_cursor VALUES(?,?)',(path,task['evidence_count'] if task.get('strategy')==STRATEGY else task.get('evidence_offset',0)+len(task.get('evidence',[]))))
        elif kind=='map_review':
            self._review_result(path,task,result,None)
            with self.db:self.db.execute('INSERT OR REPLACE INTO prep_map_reviews VALUES(?,?,?)',(path,task['plan']['version'],pack(result)))
            with self.db:
                self.db.execute("UPDATE prep_issues SET state='superseded' WHERE path=? AND chapter='map'",(path,))
                for issue in result['issues']:
                    iid=digest(['map',task['plan']['version'],issue])[:24]
                    self.db.execute('INSERT OR REPLACE INTO prep_issues VALUES(?,?,?,?,?,?,?)',(path,iid,'map','map',issue['severity'],pack(issue),'open'))
            if any(i['severity']=='blocking' for i in result['issues']):
                attempts=self.db.execute("SELECT count(*) FROM prep_map_reviews r JOIN course_plans p ON p.path=r.path AND p.version=r.version WHERE r.path=? AND COALESCE(json_extract(p.data,'$.map_repair_version'),0)=?",(path,task['plan']['data'].get('map_repair_version',0))).fetchone()[0]
                if attempts>=3:raise ValueError('La mappa richiede un chiarimento: '+result['issues'][0]['message'])
                with self.db:self.db.execute('DELETE FROM prep_map_cursor WHERE path=?',(path,))
                with self.db:
                    data=dict(task['plan']['data'],final=False,review_feedback=result)
                    self.db.execute('INSERT INTO course_plans VALUES(?,?,?,?,?)',(path,task['plan']['version']+1,pack(data),'Mappa da correggere dopo revisione',stamp()))
        elif kind in ('chapter','repair_chapter'):
            chapter=task['chapter']['id']
            for block in result.get('blocks',[]):self._prep_refs(path,task,block.get('sources',block.get('spec',{}).get('sources',[])))
            self._validate_chapter_content(path,chapter,result)
            self._deterministic_checks(result)
            previous=self.db.execute('SELECT max(revision) FROM prep_drafts WHERE path=? AND chapter=?',(path,chapter)).fetchone()[0] or 0
            deps=digest([task.get('plan',self._plan(path)),self._preference_fingerprint(p['course'])])
            with self.db:self.db.execute("UPDATE prep_issues SET state='under_review' WHERE path=? AND chapter=? AND state='needs_review'",(path,chapter))
            with self.db:self.db.execute('INSERT INTO prep_drafts VALUES(?,?,?,?,?,NULL,NULL,NULL,0)',(path,chapter,previous+1,pack(result),deps))
        elif kind.startswith('review_'):
            chapter=task['chapter']['id'];revision=task['draft_revision']
            if kind=='review_solve':
                activities=[b['id'] for b in task['draft']['blocks'] if b['kind']=='activity']
                if {a.get('block') for a in result.get('solutions',[])}!=set(activities):raise ValueError('Risolvi ogni esercizio prima di consultare le soluzioni.')
                if any('answer' not in a or not a.get('reasoning') for a in result.get('solutions',[])):raise ValueError('Ogni soluzione indipendente richiede risposta e ragionamento.')
                column='solve'
            else:
                self._review_result(path,task,result,task['draft']);column='discipline' if kind=='review_discipline' else 'didactic'
            with self.db:self.db.execute('UPDATE prep_drafts SET '+column+'=? WHERE path=? AND chapter=? AND revision=?',(pack(result),path,chapter,revision))
        elif kind=='publish':
            self._publish_reviewed(path,task)
        else:raise ValueError('Fase di preparazione sconosciuta.')
        with self.db:
            self.db.execute("UPDATE prep_tasks SET state='done',result=?,finished=?,error=NULL WHERE id=?",(pack(raw_result),stamp(),task['task_id']))
            self.db.execute('UPDATE prep_runs SET last_checkpoint=?,current=NULL,error=NULL,updated=? WHERE path=?',(stamp(),stamp(),path))
        return self.course_path_view(path)

    def _review_result(self,path,task,result,draft):
        if not isinstance(result.get('issues'),list) or not result.get('summary'):raise ValueError('Revisione senza esito e rilievi.')
        if draft:
            expected={b['id'] for b in draft['blocks']}
            refs={ref for b in draft['blocks'] for ref in b.get('sources',b.get('spec',{}).get('sources',[]))}
            if set(result.get('checked_blocks',[]))!=expected:raise ValueError('La revisione deve coprire tutti i blocchi del capitolo. Blocchi mancanti: '+pack(sorted(expected-set(result.get('checked_blocks',[]))))+'.')
            missing=refs-set(result.get('checked_sources',[]))
            if missing:raise ValueError('La revisione deve verificare le fonti dei blocchi. Fonti mancanti in checked_sources: '+pack(sorted(missing))+'. Includi anche gli originali già forniti nel compito, dopo averli confrontati; non limitarti alle letture aggiuntive via strumenti.')
            for ref in set(result.get('checked_sources',[])):self._prep_refs(path,task,[ref])
        elif task['kind']=='map_review':
            if set(result.get('checked_objectives',[]))!=set(range(len(self._path(path)['objective']['included']))):raise ValueError('La revisione deve coprire tutti gli obiettivi.')
        blocks={b['id'] for b in draft['blocks']} if draft else None
        for issue in result['issues']:
            if issue.get('severity') not in ('blocking','warning') or not issue.get('message') or (blocks is not None and issue.get('block') not in blocks):raise ValueError('Rilievo senza gravità, spiegazione o blocco valido.')
            self._prep_refs(path,task,issue.get('sources'))

    def _publish_reviewed(self,path,task):
        row=self.db.execute('SELECT * FROM prep_drafts WHERE path=? AND chapter=? AND revision=?',(path,task['chapter']['id'],task['draft_revision'])).fetchone()
        if not row or not all(row[k] for k in ('solve','discipline','didactic')):raise ValueError('Mancano le revisioni complete.')
        content=unpack(row['data']);blocked=set()
        with self.db:self.db.execute("UPDATE prep_issues SET state='superseded' WHERE path=? AND chapter=?",(path,task['chapter']['id']))
        for stage in ('discipline','didactic'):
            for issue in unpack(row[stage])['issues']:
                key=digest([task['chapter']['id'],row['revision'],issue])[:24]
                with self.db:self.db.execute('INSERT OR REPLACE INTO prep_issues VALUES(?,?,?,?,?,?,?)',(path,key,task['chapter']['id'],issue['block'],issue['severity'],pack(issue),'open'))
                if issue['severity']=='blocking':blocked.add(issue['block']);blocked.update(issue.get('depends_on',[]))
        while True:
            expanded=blocked|{b['id'] for b in content['blocks'] if set(b.get('depends_on',[]))&blocked}
            if expanded==blocked:break
            blocked=expanded
        for b in content['blocks']:
            if b['id'] in blocked:
                refs=b.get('sources') or b.get('spec',{}).get('sources',[])
                original_id=b['id'];b.clear();b.update(id=original_id,kind='text',text='Questo punto richiede un chiarimento prima di proseguire. Consulta i problemi aperti del capitolo; le altre parti restano disponibili.',sources=refs,suspended=True)
        content['review']={'status':('needs_clarification' if len(blocked)==len(content['blocks']) else 'reviewed_with_issues') if blocked else 'reviewed','discipline':'completed','didactic':'completed','blocked_blocks':list(blocked),'provisional':True}
        super()._save_chapter(path,task['chapter']['id'],content)
        with self.db:self.db.execute('UPDATE prep_drafts SET published=1 WHERE path=? AND chapter=? AND revision=?',(path,task['chapter']['id'],task['draft_revision']))

    def _deterministic_checks(self,content):
        for block in content['blocks']:
            spec=block.get('spec',{});check=spec.get('verification')
            if not check:continue
            data=check.get('input',{});model=check.get('model')
            if model=='reduction_depth':
                n=int(data['n'])
                if not 1<=n<=2**30:raise ValueError('Dimensione della riduzione non valida.')
                value=(n-1).bit_length()
            elif model=='prefix_sum':
                values=data.get('values',[])
                if not values or len(values)>10000 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in values):raise ValueError('Input prefix sum non valido.')
                value=[];total=0
                for x in values:total+=x;value.append(total)
            elif model in ('amdahl','gustafson'):
                processors=int(data['processors']);fraction=float(data['fraction'])
                if processors<1 or not 0<=fraction<=1:raise ValueError('Ipotesi dello scaling non valide.')
                value=1/((1-fraction)+fraction/processors) if model=='amdahl' else processors-fraction*(processors-1)
            else:raise ValueError('Modello di verifica deterministica non supportato.')
            expected=check.get('expected')
            equal=lambda a,b: math.isclose(float(a),float(b),rel_tol=1e-8,abs_tol=1e-9)
            valid=(len(value)==len(expected) and all(equal(a,b) for a,b in zip(value,expected))) if isinstance(value,list) and isinstance(expected,list) else equal(value,expected) if isinstance(value,(int,float)) and isinstance(expected,(int,float)) else False
            if not valid:raise ValueError('Controllo deterministico fallito nel blocco '+block['id'])
            if spec.get('kind')=='numeric' and not equal(value,spec.get('answer')):raise ValueError('Risposta numerica diversa dal risultato verificato.')
            check['status']='checked_for_declared_model'

    def preparation_evidence(self,path,limit=50,offset=0):
        self._path(path);result=[]
        for r in self.db.execute('SELECT data FROM prep_claims WHERE path=? ORDER BY rowid LIMIT ? OFFSET ?',(path,min(100000,max(1,int(limit))),max(0,int(offset)))):
            claim=unpack(r[0]);valid=True
            for did,fp in claim.get('dependencies',{}).items():
                row=self.db.execute('SELECT fingerprint FROM documents WHERE id=?',(did,)).fetchone()
                if not row or row[0]!=fp:valid=False
            if valid and any(self.db.execute("SELECT 1 FROM prep_spans WHERE path=? AND source=? AND status!='outside'",(path,ref)).fetchone() for ref in claim['sources']):
                try:
                    safe=True
                    for ref in claim['sources']:
                        source=self.source(ref,allow_solutions=False)
                        if claim.get('access_fingerprints',{}).get(ref,digest(source['text']))!=digest(source['text']):safe=False
                    if safe:result.append(claim)
                except ValueError:pass
        return result

    def preparation_decisions(self,path,limit=100,offset=0):
        self._path(path)
        return [dict(r,skills=unpack(r['skills'],[])) for r in self.db.execute('SELECT s.*,p.title,p.page,p.start,p.end,p.document FROM prep_spans s JOIN passages p ON p.id=s.source WHERE s.path=? ORDER BY p.path,p.rowid LIMIT ? OFFSET ?',(path,min(5000,max(1,int(limit))),max(0,int(offset))))]

    def preparation_decide(self,path,source,status,reason):
        if status not in STATUSES or not str(reason).strip():raise ValueError('Servono stato e motivo.')
        row=self.db.execute('SELECT 1 FROM prep_spans WHERE path=? AND source=?',(path,source)).fetchone()
        if not row:raise ValueError('Intervallo non disponibile.')
        with self.db:
            self.db.execute('UPDATE prep_spans SET status=?,reason=?,selected=1 WHERE path=? AND source=?',(status,str(reason)[:3000],path,source))
            plan=self._plan(path)
            if plan:
                data=dict(plan['data'],final=False)
                self.db.execute('INSERT INTO course_plans VALUES(?,?,?,?,?)',(path,plan['version']+1,pack(data),'Selezione corretta dallo studente',stamp()))
            self.db.execute('DELETE FROM prep_map_cursor WHERE path=?',(path,))
        return self.course_path_view(path)

    def preparation_issue(self,path,issue,note):
        if not str(note).strip():raise ValueError('Scrivi il chiarimento.')
        row=self.db.execute('SELECT * FROM prep_issues WHERE path=? AND id=?',(path,issue)).fetchone()
        if not row:raise ValueError('Problema non disponibile.')
        data=dict(unpack(row['data']),student_note=str(note)[:5000])
        with self.db:self.db.execute("UPDATE prep_issues SET data=?,state='needs_review' WHERE path=? AND id=?",(pack(data),path,issue))
        return self.course_path_view(path)

    def preparation_progress(self,path):
        run=self.db.execute('SELECT * FROM prep_runs WHERE path=?',(path,)).fetchone()
        if not run:return None
        current=self.db.execute('SELECT kind,state,started,error,attempts,metrics FROM prep_tasks WHERE id=?',(run['current'],)).fetchone() if run['current'] else None
        counts=dict(self.db.execute('SELECT state,count(*) FROM prep_tasks WHERE path=? GROUP BY state',(path,)).fetchall())
        details=dict(current) if current else None
        if details:
            metrics=unpack(details.get('metrics'),{});details['routing']=metrics.get('routing')
            repair=metrics.get('repair_checkpoint',{})
            if details['kind']=='repair_chapter' and repair.get('version')==1:
                details['repair_progress']={'done':len(repair.get('blocks',[])),'total':len(repair.get('targets',[]))}
        mapping=None
        if self._path(path)['objective'].get('map_strategy')==STRATEGY:
            row=self.db.execute('SELECT build,manifest FROM prep_map_builds WHERE path=? ORDER BY rowid DESC LIMIT 1',(path,)).fetchone()
            if row:
                manifest=unpack(row['manifest']);covered=set(manifest['covered'])
                for part in self.db.execute('SELECT data FROM prep_map_parts WHERE path=? AND build=?',(path,row['build'])):
                    covered.update(cid for a in unpack(part[0])['additions'] for cid in a['evidence'])
                mapping={'integrated':len(covered),'total':len(manifest['all_ids']),'parts_done':self.db.execute('SELECT count(*) FROM prep_map_parts WHERE path=? AND build=?',(path,row['build'])).fetchone()[0]}
        return dict(run,mapping=mapping,current_task=details,task_counts=counts,issues=[dict(r,data=unpack(r['data'])) for r in self.db.execute("SELECT * FROM prep_issues WHERE path=? AND state!='superseded' ORDER BY rowid",(path,))])

    def preparation_model_call(self,path,task,call,model,role,data):
        if not self.db.execute('SELECT 1 FROM prep_tasks WHERE id=? AND path=?',(task,path)).fetchone():raise ValueError('Compito non disponibile.')
        if not isinstance(model,dict) or not model.get('provider') or not model.get('id') or not isinstance(data,dict):raise ValueError('Dati del modello non validi.')
        with self.db:self.db.execute('INSERT OR IGNORE INTO prep_model_calls VALUES(?,?,?,?,?,?,?)',(call,path,task,pack(model),str(role)[:100],pack(data),stamp()))
        return {'saved':True}

    def preparation_reject(self,path,task,error,output):
        row=self.db.execute('SELECT state FROM prep_tasks WHERE id=? AND path=?',(task,path)).fetchone()
        if not row or row['state'] not in ('running','waiting','correcting'):raise ValueError('Compito non attivo.')
        if not isinstance(output,str) or len(output)>250000:raise ValueError('Diagnostica del provider troppo lunga.')
        with self.db:self.db.execute('INSERT INTO prep_rejections VALUES(?,?,?,?,?,?)',(ident(),path,task,str(error)[:5000],output,stamp()))
        return {'saved':True}

    def preparation_metric(self,path,task,state,error=None,metrics=None):
        if state not in ('waiting','correcting','error','paused'):raise ValueError('Stato non valido.')
        previous=self.db.execute('SELECT metrics FROM prep_tasks WHERE id=? AND path=?',(task,path)).fetchone()
        if not previous:raise ValueError('Compito non disponibile.')
        merged=dict(unpack(previous[0],{}),**(metrics or {}))
        with self.db:
            self.db.execute('UPDATE prep_tasks SET state=?,error=?,metrics=? WHERE id=? AND path=?',(state,str(error)[:3000] if error else None,pack(merged),task,path))
            if state=='error':self.db.execute('UPDATE prep_runs SET error=? WHERE path=?',(str(error)[:3000],path))
        return {'saved':True}

    def preparation_usage(self,path,task,metrics):
        row=self.db.execute('SELECT metrics FROM prep_tasks WHERE id=? AND path=?',(task,path)).fetchone()
        if not row:raise ValueError('Compito non disponibile.')
        merged=dict(unpack(row[0],{}),**metrics)
        with self.db:self.db.execute('UPDATE prep_tasks SET metrics=? WHERE id=?',(pack(merged),task))
        return {'saved':True}

    def preparation_recover(self):
        with self.db:self.db.execute("UPDATE prep_tasks SET state='paused' WHERE state IN ('running','waiting','correcting')")
        return {'recovered':True}

    def course_append(self,sid,chapter,text,sources,reason):
        link=self._path_for_session(sid)
        if not link or not self._v2(link['path']):return super().course_append(sid,chapter,text,sources,reason)
        self._refs(self.session(sid)['course'],sources)
        current=self._chapter(link['path'],chapter)
        if not current:raise ValueError('Capitolo non disponibile.')
        content=copy.deepcopy(current['content']);content.pop('review',None)
        content['blocks'].append({'id':'explanation-'+ident()[:12],'kind':'text','text':text,'sources':sources})
        self._validate_chapter_content(link['path'],chapter,content)
        revision=(self.db.execute('SELECT max(revision) FROM prep_drafts WHERE path=? AND chapter=?',(link['path'],chapter)).fetchone()[0] or 0)+1
        deps=digest([self._plan(link['path']),self._preference_fingerprint(self.session(sid)['course'])])
        with self.db:self.db.execute('INSERT INTO prep_drafts VALUES(?,?,?,?,?,NULL,NULL,NULL,0)',(link['path'],chapter,revision,pack(content),deps))
        return {'queued_for_review':True,'chapter':chapter,'revision':revision,'reason':reason}

    def course_cards(self,path,document=None,offset=0):
        if not self._v2(path):return super().course_cards(path,document,offset)
        claims=self.preparation_evidence(path,limit=100000)
        if document:claims=[c for c in claims if document in c.get('dependencies',{})]
        return claims[max(0,int(offset)):max(0,int(offset))+30]

    def view(self,sid):
        result=super().view(sid);link=self._path_for_session(sid)
        if link and self._v2(link['path']):
            plan=self._plan(link['path']);progress=self.course_progress(link['path'])
            result['progress']=[dict(progress.get(c['id'],{}),id=c['id'],label=c['title'],prerequisites=c.get('prerequisites',[]),attempts=progress.get(c['id'],{}).get('attempts',0),due=None) for c in (plan['data']['chapters'] if plan else [])]
            result['recommendation']={'action':'curriculum','reason':'Segui il punto corrente del nuovo percorso; lo storico non attribuisce competenze.','concept':link['chapter']}
        return result

    def course_evidence(self,sid,chapter=None,offset=0):
        link=self._path_for_session(sid)
        if not link or not self._v2(link['path']):return super().course_evidence(sid,chapter,offset)
        if self.session(sid)['mode']=='exam':raise ValueError('Evidenze sospese durante la simulazione.')
        args=[link['path']+':%'];query='SELECT a.* FROM attempts a WHERE a.concept LIKE ?'
        if chapter:query+=' AND a.concept=?';args.append(link['path']+':'+chapter)
        rows=self.db.execute(query+' ORDER BY a.created DESC LIMIT 20 OFFSET ?',args+[max(0,int(offset))])
        return [dict(r,answer=unpack(r['answer']),grade=unpack(r['grade'])) for r in rows]

    def read_session(self,sid,target,offset=0,limit=30,activity_offset=0,attempt_offset=0):
        for r in self.db.execute('SELECT spec FROM activities WHERE session=?',(target,)):
            for ref in unpack(r[0]).get('sources',[]):
                if self.db.execute('SELECT 1 FROM protected_spans WHERE source=?',(ref,)).fetchone():raise ValueError('Storico con quesiti riservati: escluso dal contesto del tutor.')
        result=super().read_session(sid,target,offset,limit,activity_offset,attempt_offset)
        link=self._path_for_session(target)
        if link and self._path(link['path'])['objective'].get('archived'):result['notice']='Archivio storico generato dal vecchio motore: non è una fonte accademica e non va riusato nel nuovo corso.'
        return result

    def course_path_view(self,path,sid=None):
        result=super().course_path_view(path,sid)
        if result['objective'].get('engine')!=2:return result
        decisions=self.preparation_decisions(path,limit=5000);bydoc={}
        for d in decisions:bydoc.setdefault(d['document'],[]).append(d)
        for d in result['coverage']:
            spans=bydoc.get(d['id'],[]);d.update(total=len(spans),done=sum(s['done'] for s in spans),selected=sum(s['status']!='outside' for s in spans),outside=sum(s['status']=='outside' for s in spans))
            if d['kind']=='alignment':d.update(excluded=True,structural=True)
            folder=Path(d['path']).parent.parent.name
            date=re.search(r'\d{4}-\d{2}-\d{2}',folder)
            clock=re.search(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{4}-(\d{2})-(\d{2})',folder)
            d['lesson_label']=(date[0]+(' · '+clock[1]+':'+clock[2] if clock else '')+' · Lezione') if date and d['kind'] in ('video','alignment') else None
            d['display_title']=(date[0]+(' · '+clock[1]+':'+clock[2] if clock else '')+' · '+('Trascrizione' if d['kind']=='video' else 'Collegamenti alle slide') if date and d['kind'] in ('video','alignment') else d['title'])
        result['preparation']=self.preparation_progress(path);result['decisions']=decisions
        for chapter in result['chapters']:
            detail=self._chapter(path,chapter['id'])
            chapter['review']=detail['content'].get('review') if detail else None
        return result

    def course_exam_profile(self,path,offset=0,limit=20):
        # Never infer exam frequency from a classroom question, even in archived legacy runs.
        data=super().course_exam_profile(path,0,100000)
        rows=[]
        for r in self.db.execute('SELECT q.data,d.path document_path FROM course_questions q JOIN documents d ON d.id=q.document WHERE q.path=?',(path,)):
            q=unpack(r['data'])
            if not is_exam(r['document_path']) or q.get('origin','exam')!='exam':continue
            if self._v2(path) and not q.get('authenticity_verified'):continue
            try:
                for ref in q['sources']:
                    if self.source(ref,allow_solutions=False)['kind']!='pdf':raise ValueError('Non è una prova originale.')
            except ValueError:continue
            rows.append(q)
        relevant=[q for q in rows if q.get('in_scope',True)]
        return dict(data,total=len(relevant),excluded_total=len(rows)-len(relevant),formats=dict(Counter(q['format'] for q in relevant)),skills=dict(Counter(s.casefold() for q in relevant for s in q['skills'])),questions=relevant[max(0,int(offset)):max(0,int(offset))+min(40,int(limit))],sample_size=len(rows),families=dict(Counter(q.get('family',digest(q['text'])) for q in relevant)),limitations='Ricorrenze nel campione deduplicato, non probabilità di uscita.')

    def source_visual(self,source_id):
        source=self.source(source_id,allow_solutions=False)
        if source['kind']=='pdf':return dict(self.render_pdf(source_id,allow_solutions=False),source=source_id,mimeType='image/png')
        if source['kind'] not in ('video','alignment'):raise ValueError('Nessuna immagine associata.')
        file=(self.root/source['path']).parent.parent/'video.mp4'
        if not file.is_file():raise ValueError('Video originale non disponibile.')
        raw=self.db.execute('SELECT metadata FROM passages WHERE id=?',(source_id,)).fetchone()
        alignment=unpack(raw[0],{}).get('alignment',{})
        moment=alignment.get('frame_time') if source['kind']=='alignment' else ((source['start'] or 0)+(source['end'] or source['start'] or 0))/2
        if not isinstance(moment,(int,float)) or not math.isfinite(moment):moment=source['start'] or 0
        output=self.state/'frames'/ (digest([source_id,file.stat().st_mtime_ns,moment])+'.png');output.parent.mkdir(exist_ok=True)
        if not output.exists():subprocess.run(['ffmpeg','-v','error','-ss',str(moment),'-i',str(file),'-frames:v','1',str(output)],check=True,timeout=30,capture_output=True)
        return {'path':str(output),'source':source_id,'mimeType':'image/png'}
