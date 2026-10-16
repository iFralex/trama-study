"""Versioned course curricula. All writes belong to the study bridge, never to HTML."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from collections import Counter


def stamp(): return datetime.now(timezone.utc).isoformat()
def ident(): return uuid.uuid4().hex
def pack(value): return json.dumps(value, ensure_ascii=False)
def unpack(value, default=None): return json.loads(value) if value else default

def exam_family(path):
    return re.sub(r'(?:[._ -](?:sol(?:ution)?s?|solutions|answers?))(?=\.[^.]+$)', '', path, flags=re.I)

def is_exam(path):
    if re.search(r'(?:results|risultati|elenco|esiti)',path,re.I):return False
    return bool(re.search(r'(?:exams?|esami|temi|1st.part|2nd.part|mid.term|past.papers)',path,re.I))

def shingles(text):
    text=re.sub(r'[_\s]+',' ',text.lower())
    words=re.findall(r'[a-zÀ-ÿ]+|\d+',text)
    return {' '.join(words[i:i+5]) for i in range(max(0,len(words)-4))}

class CourseStudy:
    def setup_course_study(self):
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS course_paths(id TEXT PRIMARY KEY,course TEXT,objective TEXT,status TEXT,error TEXT,created TEXT,updated TEXT);
          CREATE TABLE IF NOT EXISTS course_path_sessions(session TEXT PRIMARY KEY,path TEXT,chapter TEXT,version INTEGER,block TEXT,return_state TEXT);
          CREATE TABLE IF NOT EXISTS course_recalls(path TEXT,chapter TEXT,card TEXT,last_attempt TEXT,PRIMARY KEY(path,chapter));
          CREATE TABLE IF NOT EXISTS course_recall_runs(session TEXT PRIMARY KEY,chapter TEXT,activity TEXT,finished INTEGER DEFAULT 0);
          CREATE TABLE IF NOT EXISTS course_chapter_exposure(path TEXT,chapter TEXT,PRIMARY KEY(path,chapter));
          CREATE TABLE IF NOT EXISTS course_active_sessions(path TEXT PRIMARY KEY,session TEXT);
          CREATE TABLE IF NOT EXISTS course_positions(session TEXT,chapter TEXT,version INTEGER,block TEXT,PRIMARY KEY(session,chapter,version));
          CREATE TABLE IF NOT EXISTS course_reservation_policy(course TEXT PRIMARY KEY);
          CREATE TABLE IF NOT EXISTS course_reservations(course TEXT,document TEXT,exposed INTEGER DEFAULT 0,reason TEXT,PRIMARY KEY(course,document));
          CREATE TABLE IF NOT EXISTS course_exposure(course TEXT,document TEXT,created TEXT,PRIMARY KEY(course,document));
          CREATE TABLE IF NOT EXISTS course_units(path TEXT,id TEXT,document TEXT,source TEXT,fingerprint TEXT,start INTEGER,end INTEGER,card TEXT,PRIMARY KEY(path,id));
          CREATE TABLE IF NOT EXISTS course_documents(path TEXT,document TEXT,fingerprint TEXT,summary TEXT,integrated INTEGER DEFAULT 0,PRIMARY KEY(path,document));
          CREATE TABLE IF NOT EXISTS course_questions(path TEXT,id TEXT,document TEXT,data TEXT,PRIMARY KEY(path,id));
          CREATE TABLE IF NOT EXISTS course_plans(path TEXT,version INTEGER,data TEXT,reason TEXT,created TEXT,PRIMARY KEY(path,version));
          CREATE TABLE IF NOT EXISTS course_chapters(path TEXT,chapter TEXT,version INTEGER,content TEXT,dependencies TEXT,created TEXT,PRIMARY KEY(path,chapter,version));
          CREATE TABLE IF NOT EXISTS course_chapter_activities(session TEXT,chapter TEXT,version INTEGER,block TEXT,activity TEXT,PRIMARY KEY(session,chapter,version,block));
          CREATE TABLE IF NOT EXISTS course_journal(id TEXT PRIMARY KEY,course TEXT,path TEXT,chapter TEXT,kind TEXT,text TEXT,evidence TEXT,correction TEXT,created TEXT);
          CREATE TABLE IF NOT EXISTS course_worker_results(path TEXT,task TEXT,result TEXT,created TEXT,PRIMARY KEY(path,task));
        ''')
        if 'activity_version' not in {r[1] for r in self.db.execute('PRAGMA table_info(course_chapter_activities)')}:
            self.db.execute('ALTER TABLE course_chapter_activities ADD COLUMN activity_version INTEGER DEFAULT 1')
        self.db.execute('CREATE INDEX IF NOT EXISTS course_units_document ON course_units(path,document)')
        self.db.commit()

    def _path(self,path):
        row=self.db.execute('SELECT * FROM course_paths WHERE id=?',(path,)).fetchone()
        if not row: raise ValueError('Percorso non disponibile.')
        return dict(row,objective=unpack(row['objective'],{}))

    def _path_for_session(self,sid):
        row=self.db.execute('SELECT * FROM course_path_sessions WHERE session=?',(sid,)).fetchone()
        return dict(row) if row else None

    def _refs(self,course,refs,required=True):
        if not isinstance(refs,list) or (required and not refs) or len(refs)>30: raise ValueError('Servono fonti citabili del corso.')
        for ref in refs:
            source=self.source(ref,allow_reserved=False,allow_solutions=False)
            if source['course']!=course: raise ValueError('Fonte di un altro corso.')
        return list(dict.fromkeys(refs))

    def course_inventory(self,course):
        self.course_path(course)
        rows=self.db.execute('''SELECT d.*,min(p.kind) kind,count(p.id) passages,max(p.solution) solution,max(p.reserved) reserved,
          group_concat(DISTINCT p.quality) quality FROM documents d LEFT JOIN passages p ON p.document=d.id
          WHERE d.course=? GROUP BY d.id ORDER BY d.path''',(course,)).fetchall()
        seen={};output=[]
        for r in rows:
            item=dict(r);item['title']=r['path'].split('/')[-1];item['exam']=is_exam(r['path']) and not r['solution'];item['administrative']=bool(re.search(r'/(?:results|risultati|esiti)/|/(?:elenco|graduatoria)[._ -]',r['path'],re.I))
            if not r['passages'] and not item['issue']:item['issue']='Nessun testo estraibile: serve un originale leggibile o OCR verificato.'
            item['duplicate_of']=seen.get(r['fingerprint']) if not r['issue'] else None
            if not r['issue']: seen.setdefault(r['fingerprint'],r['id'])
            warning=self.db.execute("SELECT metadata FROM passages WHERE document=? AND instr(metadata,'\"issue\"')>0 LIMIT 1",(r['id'],)).fetchone()
            item['warning']=unpack(warning[0],{}).get('issue') if warning else None
            item['exposed']=bool(self.db.execute('SELECT 1 FROM course_exposure WHERE course=? AND document=?',(course,r['id'])).fetchone())
            if item['exam'] and self.db.execute('SELECT 1 FROM course_units WHERE document=? AND card IS NOT NULL LIMIT 1',(r['id'],)).fetchone():item['exposed']=True
            if not item['exposed'] and item['exam'] and self.db.execute('SELECT 1 FROM messages m JOIN sessions s ON s.id=m.session WHERE s.course=? AND instr(m.text,?)>0 LIMIT 1',(course,r['id']+':')).fetchone():item['exposed']=True
            # Existing activity references are evidence of exposure, even before the new journal.
            if not item['exposed'] and item['exam']:
                item['exposed']=bool(self.db.execute("""SELECT 1 FROM activities a JOIN sessions s ON s.id=a.session
                    WHERE s.course=? AND instr(a.spec,?)>0 LIMIT 1""",(course,r['id']+':')).fetchone())
            output.append(item)
        exams=[r for r in output if r['exam'] and not r['exposed'] and not r['duplicate_of'] and not r['issue']]
        proposed=[r['id'] for r in sorted(exams,key=lambda r:(not bool(r['reserved']),r['path']),reverse=False)[:2]]
        return {'documents':output,'proposed':proposed,'warnings':['Le trascrizioni parziali e le associazioni candidate richiedono confronto con gli originali.'] if any('parziale' in (r['quality'] or '') for r in rows) else []}

    def _reserve(self,course,documents):
        inventory=self.course_inventory(course)['documents'];byid={r['id']:r for r in inventory}
        if not isinstance(documents,list) or any(d not in byid or byid[d]['solution'] for d in documents): raise ValueError('Temi riservati non validi.')
        # Whole-document and page similarity detects duplicated question sheets without sending held-out text to AI.
        chosen=set(documents);held=[]
        selected_fingerprints={byid[d]['fingerprint'] for d in documents}
        for did in documents:
            held.extend(shingles(r[0]) for r in self.db.execute('SELECT text FROM passages WHERE document=?',(did,)))
        for r in inventory:
            if not r['exam'] or r['id'] in chosen: continue
            if r['fingerprint'] in selected_fingerprints:chosen.add(r['id']);continue
            sets=[shingles(p[0]) for p in self.db.execute('SELECT text FROM passages WHERE document=?',(r['id'],))]
            if any(len(a)>=15 and len(b)>=15 and len(a&b)/max(1,min(len(a),len(b)))>=.8 for a in sets for b in held): chosen.add(r['id'])
        families={exam_family(byid[d]['path']) for d in chosen}
        selected={r['id'] for r in inventory if exam_family(r['path']) in families or r['id'] in chosen}
        with self.db:
            # Reservations apply across this course's objectives to prevent another session leaking a holdout.
            self.db.execute('INSERT OR IGNORE INTO course_reservation_policy VALUES(?)',(course,))
            old={r[0] for r in self.db.execute('SELECT document FROM course_reservations WHERE course=?',(course,))}
            self.db.execute('DELETE FROM course_reservations WHERE course=?',(course,))
            for did in selected:
                r=byid[did];reason='scelto' if did in documents else 'soluzione o sovrapposizione rilevata'
                self.db.execute('INSERT INTO course_reservations VALUES(?,?,?,?)',(course,did,int(r['exposed']),reason))
            for did in old-selected:
                self.db.execute('INSERT OR IGNORE INTO course_exposure VALUES(?,?,?)',(course,did,stamp()))
            self.db.execute('UPDATE passages SET reserved=0 WHERE course=?',(course,))
            self.db.executemany('UPDATE passages SET reserved=1 WHERE document=?',[(d,) for d in selected])
        return sorted(selected)

    def course_create(self,course,request,date='',minutes=None,reserved=None):
        self.course_path(course)
        if not isinstance(request,str) or not 3<=len(request.strip())<=6000: raise ValueError('Descrivi quale esame vuoi preparare e cosa comprende.')
        path=ident();sid=ident();objective={'request':request.strip(),'date':str(date)[:40],'minutes':minutes,'confirmed':False}
        inventory=self.course_inventory(course)
        if not inventory['documents']: raise ValueError('Importa prima i materiali del corso.')
        if reserved is None: reserved=inventory['proposed']
        selected=self._reserve(course,reserved)
        objective['reserved']=selected
        objective['reserved_requested']=list(reserved)
        with self.db:
            self.db.execute('INSERT INTO course_paths VALUES(?,?,?,?,?,?,?)',(path,course,pack(objective),'scope',None,stamp(),stamp()))
            self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?)',(sid,course,request[:200],25,0,'learn',None,stamp(),stamp()))
            self.db.execute('INSERT INTO course_path_sessions VALUES(?,?,NULL,NULL,NULL,NULL)',(sid,path))
            self.db.execute('INSERT OR REPLACE INTO course_active_sessions VALUES(?,?)',(path,sid))
        self.setting('last_course',course)
        return self.course_path_view(path)

    def course_paths(self,course):
        self.course_path(course)
        return [dict(r,objective=unpack(r['objective'])) for r in self.db.execute('SELECT * FROM course_paths WHERE course=? ORDER BY updated DESC',(course,))]

    def _plan(self,path):
        row=self.db.execute('SELECT * FROM course_plans WHERE path=? ORDER BY version DESC LIMIT 1',(path,)).fetchone()
        return dict(row,data=unpack(row['data'])) if row else None

    def _chapter(self,path,chapter,version=None):
        row=self.db.execute('SELECT * FROM course_chapters WHERE path=? AND chapter=?'+(' AND version=?' if version else '')+' ORDER BY version DESC LIMIT 1',([path,chapter,version] if version else [path,chapter])).fetchone()
        return dict(row,content=unpack(row['content']),dependencies=unpack(row['dependencies'])) if row else None

    def course_path_view(self,path,sid=None):
        p=self._path(path);plan=self._plan(path)
        if sid and (not self._path_for_session(sid) or self._path_for_session(sid)['path']!=path): raise ValueError('Sessione di un altro percorso.')
        session=self._path_for_session(sid) if sid else self.db.execute('SELECT * FROM course_path_sessions WHERE path=? ORDER BY (session=(SELECT session FROM course_active_sessions WHERE path=course_path_sessions.path)) DESC,rowid DESC LIMIT 1',(path,)).fetchone()
        session=dict(session) if session else None
        coverage=[]
        inventory=self.course_inventory(p['course'])
        for d in inventory['documents']:
            counts=self.db.execute('SELECT count(*),sum(card IS NOT NULL) FROM course_units WHERE path=? AND document=?',(path,d['id'])).fetchone()
            doc=self.db.execute('SELECT fingerprint FROM course_documents WHERE path=? AND document=?',(path,d['id'])).fetchone()
            excluded=bool(d['reserved'] or d['solution'] or d['duplicate_of'] or d['issue'] or d.get('administrative'))
            coverage.append({**d,'total':counts[0],'done':counts[1] or 0,'excluded':excluded,'stale':bool(doc and doc[0]!=d['fingerprint'])})
        chapters=[];current=None;progress=self.course_progress(path)
        if plan:
            for c in plan['data'].get('chapters',[]):
                detail=self._chapter(path,c['id']);stale=bool(detail and self._chapter_stale(detail))
                chapters.append({**c,'progress':progress.get(c['id']),'ready':bool(detail),'stale':stale,'version':detail['version'] if detail else None})
            if session and session['chapter']:
                current=self._chapter(path,session['chapter'],session['version'])
                if current:
                    blocks=[]
                    for block in current['content']['blocks']:
                        if block['kind']=='activity':
                            instance=self.db.execute('SELECT activity,activity_version FROM course_chapter_activities WHERE session=? AND chapter=? AND version=? AND block=?',(session['session'],session['chapter'],current['version'],block['id'])).fetchone()
                            blocks.append({'id':block['id'],'kind':'activity','activity':instance[0] if instance else None,'activity_version':instance[1] if instance else None})
                        else: blocks.append(block)
                    current={**current,'content':{**current['content'],'blocks':blocks},'stale':self._chapter_stale(current)}
        reservations=[dict(r) for r in self.db.execute('SELECT r.*,d.path FROM course_reservations r JOIN documents d ON d.id=r.document WHERE r.course=?',(p['course'],))]
        revisions=[{'version':r['version'],'reason':r['reason'],'created':r['created']} for r in self.db.execute('SELECT * FROM course_plans WHERE path=? ORDER BY version DESC',(path,))]
        return {**p,'sid':session['session'] if session else None,'position':session,'has_completed_plan':bool(self.db.execute("SELECT 1 FROM course_plans WHERE path=? AND json_extract(data,'$.final')=1 LIMIT 1",(path,)).fetchone()),'plan':plan,'chapters':chapters,'current':current,'coverage':coverage,'reservations':reservations,'revisions':revisions,'journal':self.course_journal(p['course'],path=path),'profile':self.course_exam_profile(path),'warnings':inventory['warnings'],'recalls':self.course_recalls(path),'recall':dict(self.db.execute('SELECT * FROM course_recall_runs WHERE session=? AND finished=0',(session['session'],)).fetchone()) if session and self.db.execute('SELECT 1 FROM course_recall_runs WHERE session=? AND finished=0',(session['session'],)).fetchone() else None}

    def course_context(self,sid):
        link=self._path_for_session(sid)
        if not link or self.session(sid)['mode']=='exam': return None
        p=self._path(link['path']);plan=self._plan(p['id']);chapter=self._chapter(p['id'],link['chapter'],link['version']) if link['chapter'] else None
        if plan:
            for c in plan['data']['chapters']:
                for ref in c['sources']:self.source(ref,allow_reserved=False,allow_solutions=False)
        return {'path':p['id'],'objective':p['objective'],'plan':plan,'position':link,'chapter':chapter,'progress':self.course_progress(p['id']),'activity_states':self.course_activity_states(sid),'exam_profile':self.course_exam_profile(p['id']),
                'diary':self.course_journal(p['course'],path=p['id'],chapter=link['chapter'],limit=20),'preferences':self.course_journal(p['course'],kind='preference',limit=20),'recall':dict(self.db.execute('SELECT * FROM course_recall_runs WHERE session=? AND finished=0',(sid,)).fetchone()) if self.db.execute('SELECT 1 FROM course_recall_runs WHERE session=? AND finished=0',(sid,)).fetchone() else None}

    def course_confirm(self,path,summary=None,included=None,excluded=None,reserved=None):
        p=self._path(path);o=p['objective']
        if p['status'] not in ('confirm','clarification','scope'): raise ValueError('Per cambiare obiettivo crea un nuovo percorso, conservando questo storico.')
        if summary is not None:o['summary']=str(summary)[:6000]
        if included is not None:o['included']=included
        if excluded is not None:o['excluded']=excluded
        if not o.get('summary') or not o.get('included'): raise ValueError('Specifica il perimetro dell’esame prima di iniziare.')
        if reserved is not None:
            o['reserved']=self._reserve(p['course'],reserved);o['reserved_requested']=reserved
        o.update(confirmed=True,clarification=None)
        with self.db:self.db.execute('UPDATE course_paths SET objective=?,status=?,error=NULL,updated=? WHERE id=?',(pack(o),'reading',stamp(),path))
        self.course_sync(path)
        return self.course_path_view(path)

    def course_sync(self,path):
        p=self._path(path)
        if not p['objective'].get('confirmed'):return
        inventory=self.course_inventory(p['course'])['documents']
        with self.db:
            existing={r['document']:r['fingerprint'] for r in self.db.execute('SELECT * FROM course_documents WHERE path=?',(path,))}
            present={r['id'] for r in inventory if not(r['reserved'] or r['solution'] or r['duplicate_of'] or r['issue'] or r.get('administrative'))}
            changed=set(existing)-present|{d['id'] for d in inventory if d['id'] in present and existing.get(d['id'])!=d['fingerprint']}
            previous_plan=self._plan(path)
            if changed and previous_plan and previous_plan['data'].get('final'):
                data=dict(previous_plan['data'],final=False)
                self.db.execute('INSERT INTO course_plans VALUES(?,?,?,?,?)',(path,previous_plan['version']+1,pack(data),'Fonti cambiate: copertura da riconciliare',stamp()))
            for did in set(existing)-present:
                self.db.execute('DELETE FROM course_documents WHERE path=? AND document=?',(path,did));self.db.execute('DELETE FROM course_units WHERE path=? AND document=?',(path,did));self.db.execute('DELETE FROM course_questions WHERE path=? AND document=?',(path,did))
            for d in inventory:
                if d['id'] not in present or existing.get(d['id'])==d['fingerprint']:continue
                self.db.execute('DELETE FROM course_units WHERE path=? AND document=?',(path,d['id']));self.db.execute('DELETE FROM course_questions WHERE path=? AND document=?',(path,d['id']))
                self.db.execute('INSERT OR REPLACE INTO course_documents VALUES(?,?,?,?,0)',(path,d['id'],d['fingerprint'],pack({})))
                for source in self.db.execute('SELECT id,text FROM passages WHERE document=? ORDER BY COALESCE(page,start,0),id',(d['id'],)).fetchall():
                    for start in range(0,len(source['text']),6000):
                        end=min(len(source['text']),start+6000);unit=source['id']+':'+str(start)
                        self.db.execute('INSERT INTO course_units VALUES(?,?,?,?,?,?,?,NULL)',(path,unit,d['id'],source['id'],d['fingerprint'],start,end))

    def course_task(self,path):
        p=self._path(path);o=p['objective']
        if not o.get('confirmed'):return {'kind':'scope','objective':o,'course':p['course'],'reservation_candidates':[{'id':r['id'],'title':r['title'],'exposed':r['exposed']} for r in self.course_inventory(p['course'])['documents'] if r['exam']],'documents':[{'id':r['id'],'title':r['title'],'kind':r['kind'],'exam':r['exam']} for r in self.course_inventory(p['course'])['documents'] if not r['reserved'] and not r['solution']]}
        self.course_sync(path)
        if not self.db.execute('SELECT 1 FROM course_documents WHERE path=?',(path,)).fetchone():raise ValueError('Nessuna fonte didattica utilizzabile: importa materiali leggibili o sblocca un tema.')
        unit=self.db.execute('SELECT * FROM course_units WHERE path=? AND card IS NULL ORDER BY rowid LIMIT 1',(path,)).fetchone()
        if unit:
            rows=self.db.execute('SELECT * FROM course_units WHERE path=? AND document=? AND card IS NULL ORDER BY rowid LIMIT 4',(path,unit['document'])).fetchall()
            doc=self.db.execute('SELECT * FROM course_documents WHERE path=? AND document=?',(path,unit['document'])).fetchone()
            chunks=[]
            for r in rows:
                source=self.source(r['source'],allow_solutions=False)
                chunks.append({'unit':r['id'],'source':source['id'],'page':source['page'],'start':source['start'],'end':source['end'],'quality':source['quality'],'metadata':source['metadata'],'text':source['text'][r['start']:r['end']]})
            return {'kind':'reading','objective':o,'document':unit['document'],'fingerprint':doc['fingerprint'],'previous':unpack(doc['summary'],{}),'exam':is_exam(source['path']),'title':source['title'],'chunks':chunks}
        doc=self.db.execute('SELECT * FROM course_documents WHERE path=? AND integrated=0 ORDER BY document LIMIT 1',(path,)).fetchone()
        if doc:return {'kind':'integrate','objective':o,'document':doc['document'],'fingerprint':doc['fingerprint'],'card':unpack(doc['summary']),'draft':self._plan(path),'exam_profile':self.course_exam_profile(path)}
        plan=self._plan(path)
        if not plan or not plan['data'].get('final'):
            return {'kind':'reconcile','objective':o,'draft':plan,'exam_profile':self.course_exam_profile(path),'coverage':[{'document':r['id'],'title':r['title'],'issue':r['issue'],'quality':r['quality'],'reserved':r['reserved'],'administrative':r.get('administrative',False)} for r in self.course_inventory(p['course'])['documents']]}
        link=self.db.execute('SELECT * FROM course_path_sessions WHERE path=? ORDER BY (session=(SELECT session FROM course_active_sessions WHERE path=course_path_sessions.path)) DESC,rowid DESC LIMIT 1',(path,)).fetchone()
        chapters=plan['data']['chapters'];index=next((i for i,c in enumerate(chapters) if c['id']==(link['chapter'] if link else None)),0)
        for c in chapters[index:index+2]:
            chapter=self._chapter(path,c['id'])
            if not chapter or self._chapter_stale(chapter):
                return {'kind':'chapter','objective':o,'chapter':c,'plan':plan,'profile':self.course_exam_profile(path),'diary':self.course_journal(p['course'],path=path,chapter=c['id'],limit=12),'preferences':self.course_journal(p['course'],kind='preference',limit=12),'sources':[self.source(s,allow_solutions=False) for s in c['sources'][:8]]}
        return {'kind':'done'}

    def _validate_plan(self,path,data,previous=None,adaptive=False):
        p=self._path(path);chapters=data.get('chapters',[])
        if not isinstance(chapters,list) or not 1<=len(chapters)<=80:raise ValueError('Il piano deve contenere da 1 a 80 capitoli.')
        ids=[str(c.get('id','')) for c in chapters]
        if any(not i or len(i)>100 for i in ids) or len(set(ids))!=len(ids):raise ValueError('Identità dei capitoli non valide.')
        if len(pack(data))>130000:raise ValueError('Piano troppo grande: sintetizza le schede, conserva i dettagli nelle fonti.')
        seen=set()
        for c in chapters:
            if not c.get('title') or not c.get('objective') or not c.get('priority_reason') or not c.get('assessment'):raise ValueError('Ogni capitolo richiede titolo, obiettivo, priorità motivata e progetto degli esercizi.')
            self._refs(p['course'],c.get('sources'))
            if not isinstance(c.get('prerequisites',[]),list) or any(i not in seen for i in c.get('prerequisites',[])):raise ValueError('Prerequisiti mancanti, ciclici o successivi al capitolo.')
            seen.add(c['id'])
        if previous:
            old={c['id']:c for c in previous['data']['chapters']};new={c['id']:c for c in chapters}
            if not set(old)<=set(new):raise ValueError('Non eliminare capitoli: il cambio di perimetro richiede conferma dell’utente.')
            if adaptive:
                studied={r[0] for r in self.db.execute('SELECT DISTINCT chapter FROM course_chapter_exposure WHERE path=?',(path,))}
                if any(old[i]!=new.get(i) for i in studied if i in old):raise ValueError('Conserva le schede dei capitoli già prodotti; aggiungi recuperi o approfondimenti versionati.')
        return data

    def _check_coverage(self,path,data):
        documents={r[0] for r in self.db.execute('SELECT document FROM course_documents WHERE path=?',(path,))}
        covered={d for c in data['chapters'] for d in c.get('coverage',[])}
        outside=data.get('outside_scope',[])
        if any(not isinstance(d,dict) or not d.get('reason') or d.get('document') not in documents for d in outside):raise ValueError('Ogni esclusione richiede documento e motivo.')
        missing=documents-covered-{d['document'] for d in outside}
        if missing:raise ValueError('Copertura incompleta: collega al piano o motiva l’esclusione dei documenti '+', '.join(sorted(missing)))

    def course_commit(self,path,task,result):
        p=self._path(path);taskkey=hashlib.sha256(pack(task).encode()).hexdigest()
        completed=self.db.execute('SELECT result FROM course_worker_results WHERE path=? AND task=?',(path,taskkey)).fetchone()
        if completed:
            if unpack(completed[0])!=result:raise ValueError('Checkpoint già completato con un risultato diverso.')
            return self.course_path_view(path)
        current=self.course_task(path)
        if task.get('kind')=='reading' and [c['unit'] for c in current.get('chunks',[])]!=[c['unit'] for c in task.get('chunks',[])]:raise ValueError('Blocco di lettura obsoleto: riprendi la fase aggiornata.')
        # A paused/changed job cannot publish an obsolete batch.
        if (current.get('plan') or current.get('draft') or {}).get('version')!=(task.get('plan') or task.get('draft') or {}).get('version'):raise ValueError('Il piano è cambiato durante la generazione: riprendi la fase aggiornata.')
        if current.get('kind')!=task.get('kind') or (current.get('document'),current.get('fingerprint'))!=(task.get('document'),task.get('fingerprint')) or current.get('chapter')!=task.get('chapter'):
            raise ValueError('Risultato obsoleto: riprendi la preparazione aggiornata.')
        kind=task['kind'];taskkey=hashlib.sha256(pack(task).encode()).hexdigest()
        if kind=='scope':
            required=['summary','included','excluded','clarification']
            if any(k not in result for k in required) or not isinstance(result['included'],list) or not isinstance(result['excluded'],list):raise ValueError('Scheda dell’obiettivo incompleta.')
            recommendations=result.get('recommended_reservations',[])
            ids={r['id'] for r in self.course_inventory(p['course'])['documents'] if not r['solution']}
            if not isinstance(recommendations,list) or len(recommendations)>2 or any(not isinstance(r,dict) or r.get('document') not in ids or not r.get('reason') for r in recommendations):raise ValueError('Suggerimenti sui temi riservati non validi.')
            o=dict(p['objective'],**{k:result[k] for k in required},recommended_reservations=recommendations)
            status='clarification' if result['clarification'] else 'confirm'
            with self.db:self.db.execute('UPDATE course_paths SET objective=?,status=?,error=NULL WHERE id=?',(pack(o),status,path))
        elif kind=='reading':
            if not result.get('summary') or len(pack(result))>16000:raise ValueError('Scheda fonte mancante o troppo lunga.')
            refs=self._refs(p['course'],result.get('sources'))
            allowed={c['source'] for c in task['chunks']}|set(task['previous'].get('sources',[]))
            if not set(refs)<=allowed:raise ValueError('La scheda deve citare i passaggi effettivamente letti.')
            questions=result.get('questions',[])
            for q in questions:
                if not q.get('text') or q.get('format') not in ('choice','numeric','open','code','mixed') or not q.get('skills'):raise ValueError('Profilo del quesito incompleto.')
                if not isinstance(q.get('text'),str) or not isinstance(q.get('skills'),list) or any(not isinstance(s,str) for s in q['skills']):raise ValueError('Testo o competenze del quesito non validi.')
                if not isinstance(q.get('in_scope'),bool):raise ValueError('Indica se ogni quesito è pertinente all’obiettivo, con in_scope booleano.')
                self._refs(p['course'],q.get('sources'))
                if not set(q['sources'])<=allowed:raise ValueError('Quesito non presente nei passaggi letti.')
            with self.db:
                for c in task['chunks']:self.db.execute('UPDATE course_units SET card=? WHERE path=? AND id=?',(pack(result),path,c['unit']))
                self.db.execute('UPDATE course_documents SET summary=? WHERE path=? AND document=?',(pack(result),path,task['document']))
                for q in questions:
                    qid=hashlib.sha256(re.sub(r'\W+',' ',q['text'].lower()).encode()).hexdigest()[:24]
                    existing=self.db.execute('SELECT id,data FROM course_questions WHERE path=? AND id=?',(path,qid)).fetchone()
                    if not existing:
                        words=shingles(q['text'])
                        for old in self.db.execute('SELECT id,data FROM course_questions WHERE path=?',(path,)).fetchall():
                            oldq=unpack(old['data']);oldwords=shingles(oldq['text'])
                            if len(words)>=10 and len(oldwords)>=10 and len(words&oldwords)/max(1,min(len(words),len(oldwords)))>=.85:existing=old;break
                    if existing:
                        oldq=unpack(existing['data']);occurrences=oldq.get('occurrences',[])
                        occurrence={'document':task['document'],'sources':q['sources']}
                        if occurrence not in occurrences:occurrences.append(occurrence)
                        oldq['occurrences']=occurrences
                        self.db.execute('UPDATE course_questions SET data=? WHERE path=? AND id=?',(pack(oldq),path,existing['id']))
                    else:
                        q=dict(q,occurrences=[{'document':task['document'],'sources':q['sources']}])
                        self.db.execute('INSERT INTO course_questions VALUES(?,?,?,?)',(path,qid,task['document'],pack(q)))
        elif kind in ('integrate','reconcile'):
            previous=self._plan(path);data=self._validate_plan(path,result,previous)
            data=dict(data,final=kind=='reconcile')
            if kind=='reconcile':
                if not isinstance(data.get('gaps'),list):raise ValueError('Esplicita le lacune, anche se l’elenco è vuoto.')
                self._check_coverage(path,data)
            with self.db:
                self.db.execute('INSERT INTO course_plans VALUES(?,?,?,?,?)',(path,previous['version']+1 if previous else 1,pack(data),'Integrazione fonte' if kind=='integrate' else 'Riconciliazione e copertura',stamp()))
                if kind=='integrate':self.db.execute('UPDATE course_documents SET integrated=1 WHERE path=? AND document=?',(path,task['document']))
                else:self.db.execute('UPDATE course_paths SET status=? WHERE id=?',('ready',path))
        elif kind=='chapter':self._save_chapter(path,task['chapter']['id'],result)
        else:raise ValueError('Fase non valida.')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO course_worker_results VALUES(?,?,?,?)',(path,taskkey,pack(result),stamp()))
            self.db.execute('UPDATE course_paths SET error=NULL,updated=? WHERE id=?',(stamp(),path))
        return self.course_path_view(path)

    def _save_chapter(self,path,chapter,content):
        p=self._path(path);plan=self._plan(path);blueprint=next((c for c in plan['data']['chapters'] if c['id']==chapter),None)
        if not blueprint:raise ValueError('Capitolo non presente nel piano.')
        blocks=content.get('blocks',[])
        if not blocks or len(blocks)>24 or len(pack(content))>180000:raise ValueError('Contenuto del capitolo non valido.')
        if len({b.get('id') for b in blocks})!=len(blocks):raise ValueError('Identità dei blocchi duplicate.')
        dependencies={'@preferences:'+p['course']:self._preference_fingerprint(p['course']),'@blueprint':hashlib.sha256(pack(blueprint).encode()).hexdigest()}
        for b in blocks:
            if not b.get('id') or b.get('kind') not in ('text','activity'):raise ValueError('Blocco non valido.')
            refs=self._refs(p['course'],b.get('sources',[]) if b['kind']=='text' else b.get('spec',{}).get('sources',[]))
            for s in refs:
                source=self.source(s,allow_solutions=False);doc=self.db.execute('SELECT fingerprint FROM documents WHERE id=?',(source['document'],)).fetchone()
                dependencies[source['document']]=doc[0]
            visible=b.get('text','') if b['kind']=='text' else b.get('spec',{}).get('prompt','')
            if not set(re.findall(r'\]\(source:([^\s)]+)\)',visible))<=set(refs):raise ValueError('Citazione non presente nelle fonti del blocco.')
            if b['kind']=='text' and not b.get('text'):raise ValueError('Spiegazione vuota.')
            if b['kind']=='activity':
                spec=b['spec']
                if spec.get('kind') not in ('choice','numeric','open','completion','html'):raise ValueError('Esercizio non valido.')
                if not all(spec.get(k) for k in ('title','prompt','solution','rubric','assumptions','origin')):raise ValueError('Prepara ipotesi, provenienza, soluzione e criteri prima dell’esercizio.')
                if spec['origin'] not in ('generated','adapted','authentic'):raise ValueError('Provenienza non valida.')
                if spec['kind']=='choice' and (not spec.get('options') or spec.get('answer') not in spec['options']):raise ValueError('Scelta multipla senza risposta valida.')
                if spec['kind']=='numeric':
                    try:float(spec['answer'])
                    except (ValueError,TypeError,KeyError):raise ValueError('Risposta numerica mancante.')
                if spec['kind']=='html' and not all(spec.get(k) for k in ('html','fallback','model')):raise ValueError('HTML richiede modello dichiarato e alternativa testuale.')
        previous=self._chapter(path,chapter);version=previous['version']+1 if previous else 1
        with self.db:self.db.execute('INSERT INTO course_chapters VALUES(?,?,?,?,?,?)',(path,chapter,version,pack(content),pack(dependencies),stamp()))
        return version

    def _chapter_stale(self,chapter):
        studied=self.db.execute('SELECT 1 FROM course_chapter_exposure WHERE path=? AND chapter=?',(chapter['path'],chapter['chapter'])).fetchone()
        for did,fingerprint in chapter['dependencies'].items():
            if did.startswith('@preferences:'):
                if not studied and fingerprint!=self._preference_fingerprint(did.split(':',1)[1]):return True
                continue
            if did=='@blueprint':
                plan=self._plan(chapter['path']);blueprint=next((c for c in plan['data']['chapters'] if c['id']==chapter['chapter']),None)
                if not studied and fingerprint!=hashlib.sha256(pack(blueprint).encode()).hexdigest():return True
                continue
            row=self.db.execute('SELECT fingerprint FROM documents WHERE id=?',(did,)).fetchone()
            reserved=self.db.execute('SELECT 1 FROM passages WHERE document=? AND reserved=1',(did,)).fetchone()
            if not row or row[0]!=fingerprint or reserved:return True
        return False

    def course_exam_profile(self,path,offset=0,limit=20):
        p=self._path(path)
        rows=[unpack(r[0]) for r in self.db.execute('SELECT q.data FROM course_questions q WHERE q.path=? AND NOT EXISTS (SELECT 1 FROM passages p WHERE p.document=q.document AND p.reserved=1) ORDER BY q.id',(path,))]
        excluded_total=sum(not q.get('in_scope',True) for q in rows)
        rows=[q for q in rows if q.get('in_scope',True)]
        counts=Counter(q['format'] for q in rows);skills=Counter(s.strip().casefold() for q in rows for s in q.get('skills',[]))
        return {'total':len(rows),'excluded_total':excluded_total,'formats':dict(counts),'skills':dict(skills),'questions':rows[max(0,int(offset)):max(0,int(offset))+min(40,max(1,int(limit)))]}

    def course_status(self,path,status,error=None):
        self._path(path)
        if status not in ('running','paused','error','ready'):raise ValueError('Stato non valido.')
        with self.db:self.db.execute('UPDATE course_paths SET status=?,error=?,updated=? WHERE id=?',(status,str(error)[:1000] if error else None,stamp(),path))
        return self.course_path_view(path)

    def course_open(self,path,sid=None,fresh=False):
        p=self._path(path)
        if sid is None:
            row=self.db.execute('SELECT * FROM course_path_sessions WHERE path=? ORDER BY (session=(SELECT session FROM course_active_sessions WHERE path=course_path_sessions.path)) DESC,rowid DESC LIMIT 1',(path,)).fetchone();sid=row['session']
        if not self._path_for_session(sid) or self._path_for_session(sid)['path']!=path:raise ValueError('Sessione di un altro percorso.')
        if fresh:
            previous=self._path_for_session(sid);sid=ident()
            with self.db:
                self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?)',(sid,p['course'],p['objective'].get('summary',p['objective']['request'])[:200],25,0,'learn',None,stamp(),stamp()))
                self.db.execute('INSERT INTO course_path_sessions VALUES(?,?,?,?,?,NULL)',(sid,path,previous['chapter'],previous['version'],previous['block']))
        if not self._path_for_session(sid) or self._path_for_session(sid)['path']!=path:raise ValueError('Sessione di un altro percorso.')
        self.setting('last_course',p['course'])
        with self.db:self.db.execute('INSERT OR REPLACE INTO course_active_sessions VALUES(?,?)',(path,sid))
        plan=self._plan(path)
        if plan and (plan['data'].get('final') or self.db.execute("SELECT 1 FROM course_plans WHERE path=? AND json_extract(data,'$.final')=1 LIMIT 1",(path,)).fetchone()):
            link=self._path_for_session(sid)
            chapter=link['chapter'] or plan['data']['chapters'][0]['id']
            if self._chapter(path,chapter):self.course_select(sid,chapter)
        return self.view(sid)

    def course_select(self,sid,chapter,block=None,version=None):
        link=self._path_for_session(sid)
        if not link:raise ValueError('Sessione fuori dal percorso.')
        detail=self._chapter(link['path'],chapter,version)
        if not detail:return self.course_focus(sid,chapter)
        with self.db:self.db.execute('INSERT OR REPLACE INTO course_active_sessions VALUES(?,?)',(link['path'],sid))
        # Keep the pinned version on resume; a new version is an explicit selection.
        if version is None and link['chapter']==chapter and link['version']:detail=self._chapter(link['path'],chapter,link['version'])
        if self._chapter_stale(detail):raise ValueError('Le fonti sono cambiate: prepara e apri la versione aggiornata del capitolo.')
        ids=[b['id'] for b in detail['content']['blocks']]
        if block is not None and block not in ids:raise ValueError('Punto del capitolo non valido.')
        for b in detail['content']['blocks']:
            if b['kind']!='activity':continue
            existing=self.db.execute('SELECT activity,activity_version FROM course_chapter_activities WHERE session=? AND chapter=? AND version=? AND block=?',(sid,chapter,detail['version'],b['id'])).fetchone()
            if not existing:
                spec=dict(b['spec'],concept=link['path']+':'+chapter,grading_origin='generated',curriculum={'path':link['path'],'chapter':chapter,'version':detail['version'],'block':b['id']})
                previous=self.db.execute('SELECT activity,activity_version FROM course_chapter_activities WHERE session=? AND chapter=? AND block=? ORDER BY version DESC LIMIT 1',(sid,chapter,b['id'])).fetchone()
                reuse=None
                if previous:
                    old=self.activity(sid,previous['activity'],previous['activity_version'])['spec']
                    if old.get('kind')==spec.get('kind') and old.get('prompt')==spec.get('prompt'):reuse=previous['activity']
                a=self._activity(sid,spec,activity_id=reuse)
                with self.db:self.db.execute('INSERT INTO course_chapter_activities(session,chapter,version,block,activity,activity_version) VALUES(?,?,?,?,?,?)',(sid,chapter,detail['version'],b['id'],a['id'],a['version']))
        previous_position=self.db.execute('SELECT block FROM course_positions WHERE session=? AND chapter=? AND version=?',(sid,chapter,detail['version'])).fetchone()
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO course_chapter_exposure VALUES(?,?)',(link['path'],chapter))
            if link['chapter'] and link['version']:self.db.execute('INSERT OR REPLACE INTO course_positions VALUES(?,?,?,?)',(sid,link['chapter'],link['version'],link['block']))
            self.db.execute('UPDATE course_path_sessions SET chapter=?,version=?,block=? WHERE session=?',(chapter,detail['version'],block or (link['block'] if link['chapter']==chapter and link['version']==detail['version'] else None) or (previous_position[0] if previous_position else None) or ids[0],sid))
            self.db.execute('UPDATE sessions SET current=NULL,updated=? WHERE id=?',(stamp(),sid))
        return self.view(sid)

    def course_position(self,sid,block):
        link=self._path_for_session(sid)
        if not link or not link['chapter']:raise ValueError('Apri prima un capitolo.')
        detail=self._chapter(link['path'],link['chapter'],link['version'])
        if block not in {b['id'] for b in detail['content']['blocks']}:raise ValueError('Punto non valido.')
        with self.db:self.db.execute('UPDATE course_path_sessions SET block=? WHERE session=?',(block,sid))
        with self.db:self.db.execute('INSERT OR REPLACE INTO course_positions VALUES(?,?,?,?)',(sid,link['chapter'],link['version'],block))
        return {'saved':True}

    def course_detour(self,sid,chapter=None):
        link=self._path_for_session(sid)
        if not link:raise ValueError('Percorso non disponibile.')
        if chapter:
            state={k:link[k] for k in ('chapter','version','block')}
            result=self.course_select(sid,chapter)
            with self.db:self.db.execute('UPDATE course_path_sessions SET return_state=? WHERE session=?',(pack(state),sid))
        else:
            state=unpack(link['return_state'])
            if not state:raise ValueError('Nessuna deviazione da cui tornare.')
            result=self.course_select(sid,**state)
            with self.db:self.db.execute('UPDATE course_path_sessions SET return_state=NULL WHERE session=?',(sid,))
        return self.view(sid)

    def course_journal(self,course,path=None,chapter=None,kind=None,limit=40):
        clauses=['(course=? OR course=?)'];args=[course,'*']
        if path:clauses.append('(path=? OR path IS NULL OR kind=\'preference\')');args.append(path)
        if chapter:clauses.append('(chapter=? OR chapter IS NULL OR kind=\'preference\')');args.append(chapter)
        if kind:clauses.append('kind=?');args.append(kind)
        rows=self.db.execute('SELECT * FROM course_journal WHERE '+' AND '.join(clauses)+' ORDER BY created DESC LIMIT ?',args+[min(100,max(1,int(limit)))]).fetchall()
        return [dict(r,evidence=unpack(r['evidence'],[])) for r in rows]

    def course_note(self,sid,kind,text,evidence=None,chapter=None,global_preference=False,agent=False):
        s=self.session(sid);link=self._path_for_session(sid)
        if s['mode']=='exam':raise ValueError('Diario sospeso durante la simulazione.')
        if kind not in ('hypothesis','preference','decision') or not isinstance(text,str) or not text.strip() or len(text)>4000:raise ValueError('Nota non valida.')
        evidence=evidence or []
        if kind=='hypothesis' and not evidence:raise ValueError('Un’interpretazione richiede evidenze verificabili.')
        for e in evidence:
            found=self.db.execute('SELECT 1 FROM attempts a JOIN sessions s ON s.id=a.session WHERE a.id=? AND s.course=? UNION SELECT 1 FROM events e JOIN sessions s ON s.id=e.session WHERE e.id=? AND s.course=? UNION SELECT 1 FROM messages m JOIN sessions s ON s.id=m.session WHERE m.id=? AND s.course=?',(e,s['course'],e,s['course'],e,s['course'])).fetchone()
            if not found:raise ValueError('Evidenza non disponibile nel corso.')
        if agent and kind=='preference' and not any(self.db.execute("SELECT 1 FROM messages WHERE id=? AND role='user'",(e,)).fetchone() for e in evidence):raise ValueError('Una preferenza dichiarata richiede il messaggio dello studente come evidenza.')
        if agent and global_preference:raise ValueError('Le preferenze globali si impostano esplicitamente nell’interfaccia.')
        if global_preference and kind!='preference':raise ValueError('Solo le preferenze esplicite possono essere globali.')
        nid=ident()
        with self.db:self.db.execute('INSERT INTO course_journal VALUES(?,?,?,?,?,?,?,?,?)',(nid,'*' if global_preference else s['course'],link['path'] if link else None,chapter or (link['chapter'] if link else None),kind,text,pack(evidence),None,stamp()))
        return {'id':nid}

    def course_correct_note(self,course,note,text):
        row=self.db.execute('SELECT * FROM course_journal WHERE id=? AND course IN (?,?)',(note,course,'*')).fetchone()
        if not row or not text.strip():raise ValueError('Nota o correzione non valida.')
        with self.db:self.db.execute('UPDATE course_journal SET correction=? WHERE id=?',(text[:4000],note))
        return {'saved':True}

    def course_evidence(self,sid,chapter=None,offset=0):
        s=self.session(sid)
        if s['mode']=='exam':raise ValueError('Evidenze sospese durante la simulazione.')
        args=[s['course']];query="SELECT a.* FROM attempts a JOIN sessions s ON s.id=a.session JOIN activities v ON v.id=a.activity AND v.version=a.version WHERE s.course=? AND s.mode='learn' AND NOT EXISTS (SELECT 1 FROM json_each(v.spec,'$.sources') j JOIN passages p ON p.id=j.value WHERE p.reserved=1)"
        if chapter:
            link=self._path_for_session(sid)
            query+=' AND a.concept=?';args.append((link['path']+':'+chapter) if link and not chapter.startswith(link['path']+':') else chapter)
        rows=self.db.execute(query+' ORDER BY a.created DESC LIMIT 20 OFFSET ?',args+[max(0,int(offset))]).fetchall()
        return [dict(r,answer=unpack(r['answer']),grade=unpack(r['grade'])) for r in rows]

    def course_record_event(self,sid,aid,version,event_id,kind,result):
        link=self._path_for_session(sid)
        if not link or kind not in ('submit','hint','solution','explain'):return
        s=self.session(sid);a=self.activity(sid,aid,version);chapter=a['spec'].get('curriculum',{}).get('chapter',link['chapter'])
        text='Risposta consegnata' if kind=='submit' else {'hint':'Indizio richiesto','solution':'Soluzione richiesta','explain':'Spiegazione richiesta'}[kind]
        attempt=result.get('attempt')
        if attempt:
            self.db.execute('UPDATE course_recall_runs SET finished=1 WHERE session=? AND activity=?',(sid,aid))
        if attempt:text+='; '+str(attempt['aids'])+' aiuti; giudizio '+attempt['grade']['status']
        with self.db:self.db.execute('INSERT OR IGNORE INTO course_journal VALUES(?,?,?,?,?,?,?,?,?)',('event:'+event_id,s['course'],link['path'],chapter,'fact',text,pack([attempt['id'] if attempt else event_id]),None,stamp()))

    def course_revise(self,sid,data,reason,evidence=None):
        link=self._path_for_session(sid)
        if not link or self.session(sid)['mode']=='exam':raise ValueError('Percorso non modificabile.')
        previous=self._plan(link['path'])
        if not previous or not previous['data'].get('final'):raise ValueError('Completa prima il piano iniziale.')
        if not reason or not evidence:raise ValueError('La revisione richiede una ragione e tentativi o richieste dello studente.')
        data=self._validate_plan(link['path'],data,previous,adaptive=True);data=dict(data,final=True)
        self._check_coverage(link['path'],data)
        self.course_note(sid,'decision',reason,evidence)
        with self.db:self.db.execute('INSERT INTO course_plans VALUES(?,?,?,?,?)',(link['path'],previous['version']+1,pack(data),reason[:2000],stamp()))
        return self.course_path_view(link['path'],sid)

    def course_undo(self,path,version):
        p=self._path(path);current=self._plan(path)
        target=self.db.execute('SELECT data FROM course_plans WHERE path=? AND version=?',(path,int(version))).fetchone()
        if not target or not unpack(target[0]).get('final'):raise ValueError('Revisione non ripristinabile.')
        with self.db:self.db.execute('INSERT INTO course_plans VALUES(?,?,?,?,?)',(path,current['version']+1,target[0],'Ripristino della revisione '+str(version),stamp()))
        return self.course_path_view(path)

    def course_append(self,sid,chapter,text,sources,reason):
        link=self._path_for_session(sid)
        if not link or self.session(sid)['mode']=='exam':raise ValueError('Percorso non disponibile.')
        old=self._chapter(link['path'],chapter)
        if not old:raise ValueError('Capitolo non disponibile.')
        content=json.loads(pack(old['content']));content['blocks'].append({'id':ident(),'kind':'text','text':text,'sources':sources})
        version=self._save_chapter(link['path'],chapter,content)
        self.course_note(sid,'decision',reason or 'Approfondimento aggiunto al capitolo')
        return {'version':version,'message':'Approfondimento salvato; la versione precedente e i tentativi rimangono disponibili.'}

    def course_simulation(self,path,document):
        p=self._path(path)
        row=self.db.execute('SELECT * FROM course_reservations WHERE course=? AND document=?',(p['course'],document)).fetchone()
        sources=self.db.execute('SELECT * FROM passages WHERE document=? AND solution=0 ORDER BY page',(document,)).fetchall()
        if not row or not sources:raise ValueError('Tema non riservato disponibile.')
        sid=ident()
        with self.db:self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?)',(sid,p['course'],'Simulazione autonoma',60,0,'exam',None,stamp(),stamp()))
        self._activity(sid,{'kind':'open','title':'Simulazione · '+sources[0]['title'],'prompt':'\n\n'.join(r['text'] for r in sources),'sources':[r['id'] for r in sources],'concept':'exam:'+document,'rubric':'Correggere solo alla consegna; valutazione provvisoria.','grading_origin':'generated','simulation_path':path})
        with self.db:
            self.db.execute('UPDATE course_reservations SET exposed=1 WHERE course=? AND document=?',(p['course'],document))
            self.db.execute('INSERT OR IGNORE INTO course_exposure VALUES(?,?,?)',(p['course'],document,stamp()))
        return self.view(sid)

    def course_unlock(self,path,document):
        p=self._path(path)
        ids=[r[0] for r in self.db.execute("SELECT document FROM course_reservations WHERE course=? AND reason='scelto'",(p['course'],))]
        doc=self.db.execute('SELECT path FROM documents WHERE id=? AND course=?',(document,p['course'])).fetchone()
        if not doc:raise ValueError('Documento non disponibile.')
        family=exam_family(doc[0]);keep=[d for d in ids if exam_family(self.db.execute('SELECT path FROM documents WHERE id=?',(d,)).fetchone()[0])!=family]
        self._reserve(p['course'],keep)
        self.course_sync(path)
        return self.course_path_view(path)

    def course_context_public(self,sid):
        link=self._path_for_session(sid)
        if not link or self.session(sid)['mode']=='exam':return None
        # The browser receives no private solutions/rubrics from chapter storage.
        return {'path':link['path'],'chapter':link['chapter'],'version':link['version'],'block':link['block'],'recall':bool(self.db.execute('SELECT 1 FROM course_recall_runs WHERE session=? AND finished=0',(sid,)).fetchone())}

    def course_expose(self,course,document):
        if not self.db.execute('SELECT 1 FROM documents WHERE id=? AND course=?',(document,course)).fetchone():raise ValueError('Documento non disponibile.')
        with self.db:self.db.execute('INSERT OR IGNORE INTO course_exposure VALUES(?,?,?)',(course,document,stamp()))
        return {'saved':True}

    def course_focus(self,sid,chapter):
        link=self._path_for_session(sid)
        if not link:raise ValueError('Sessione fuori dal percorso.')
        plan=self._plan(link['path'])
        if not plan or chapter not in {c['id'] for c in plan['data']['chapters']}:raise ValueError('Capitolo fuori dal piano.')
        with self.db:
            if link['chapter'] and link['version']:self.db.execute('INSERT OR REPLACE INTO course_positions VALUES(?,?,?,?)',(sid,link['chapter'],link['version'],link['block']))
            self.db.execute('UPDATE course_path_sessions SET chapter=?,version=NULL,block=NULL WHERE session=?',(chapter,sid))
        return self.view(sid)

    def course_apply_reservations(self,course):
        if self.db.execute('SELECT 1 FROM course_reservation_policy WHERE course=?',(course,)).fetchone():
            requested=[r[0] for r in self.db.execute("SELECT r.document FROM course_reservations r JOIN documents d ON d.id=r.document WHERE r.course=? AND r.reason='scelto'",(course,))]
            self._reserve(course,requested)

    def _preference_fingerprint(self,course):
        return hashlib.sha256(pack(self.course_journal(course,kind='preference',limit=100)).encode()).hexdigest()

    def course_recalls(self,path):
        self._path(path)
        return [dict(r,card=unpack(r['card'])) for r in self.db.execute('SELECT * FROM course_recalls WHERE path=?',(path,))]

    def course_recall_card(self,sid,attempt_id,card=None):
        a=self.db.execute('SELECT * FROM attempts WHERE id=? AND session=?',(attempt_id,sid)).fetchone()
        link=self._path_for_session(sid)
        if not a or not link:return None
        activity=self.activity(sid,a['activity'],a['version']);chapter=activity['spec'].get('curriculum',{}).get('chapter')
        if not chapter:return None
        grade=unpack(a['grade']);old=self.db.execute('SELECT * FROM course_recalls WHERE path=? AND chapter=?',(link['path'],chapter)).fetchone()
        duplicate=bool(old and old['last_attempt']==attempt_id)
        if card is not None:
            if a['correction'] or grade.get('correct') not in (True,False) or duplicate:return {'duplicate':duplicate}
            if old:
                previous=self.db.execute('SELECT created FROM attempts WHERE id=?',(old['last_attempt'],)).fetchone()
                if previous and previous[0]>a['created']:return {'duplicate':True}
            if not isinstance(card,dict) or not card.get('due'):raise ValueError('Scheda di richiamo non valida.')
            with self.db:self.db.execute('INSERT OR REPLACE INTO course_recalls VALUES(?,?,?,?)',(link['path'],chapter,pack(dict(card,provisional=grade['status']!='verified')),attempt_id))
        return {'card':unpack(old['card']) if old else None,'correct':grade.get('correct') if not a['correction'] else None,'aids':a['aids'],'duplicate':duplicate}

    def course_create_recall(self,sid,chapter,spec):
        link=self._path_for_session(sid)
        if not link or self.session(sid)['mode']=='exam':raise ValueError('Percorso non disponibile.')
        plan=self._plan(link['path']);blueprint=next((c for c in plan['data']['chapters'] if c['id']==chapter),None)
        if not blueprint:raise ValueError('Capitolo non disponibile.')
        self._refs(self.session(sid)['course'],spec.get('sources'))
        if not set(spec['sources'])&set(blueprint['sources']):raise ValueError('Richiamo non ancorato al capitolo.')
        if spec.get('kind') not in ('open','choice','numeric','completion') or not all(spec.get(k) for k in ('prompt','title','solution','rubric','assumptions','origin')):raise ValueError('Richiamo incompleto.')
        canonical=re.sub(r'\W+',' ',spec['prompt'].lower())
        for row in self.db.execute('SELECT a.spec FROM activities a JOIN sessions s ON s.id=a.session WHERE s.course=?',(self.session(sid)['course'],)):
            if re.sub(r'\W+',' ',unpack(row[0]).get('prompt','').lower())==canonical:raise ValueError('Il richiamo deve essere diverso dai problemi già proposti.')
        activity=self._activity(sid,dict(spec,concept=link['path']+':'+chapter,grading_origin='generated',curriculum={'path':link['path'],'chapter':chapter,'recall':True}))
        with self.db:self.db.execute('INSERT OR REPLACE INTO course_recall_runs VALUES(?,?,?,0)',(sid,chapter,activity['id']))
        return self.view(sid)

    def course_exit_recall(self,sid):
        if not self._path_for_session(sid):raise ValueError('Percorso non disponibile.')
        with self.db:self.db.execute('UPDATE course_recall_runs SET finished=1 WHERE session=?',(sid,))
        return self.view(sid)

    def course_note_evidence(self,course,note):
        row=self.db.execute('SELECT * FROM course_journal WHERE id=? AND course IN (?,?)',(note,course,'*')).fetchone()
        if not row:raise ValueError('Nota non disponibile.')
        result=[]
        for ref in unpack(row['evidence'],[]):
            a=self.db.execute('SELECT a.* FROM attempts a JOIN sessions s ON s.id=a.session WHERE a.id=? AND s.course=?',(ref,course)).fetchone()
            if a:
                spec=self.activity(a['session'],a['activity'],a['version'])['spec']
                result.append({'id':ref,'kind':'attempt','question':spec['prompt'],'answer':unpack(a['answer']),'grade':unpack(a['grade']),'aids':a['aids'],'correction':a['correction'],'created':a['created']});continue
            e=self.db.execute('SELECT e.* FROM events e JOIN sessions s ON s.id=e.session WHERE e.id=? AND s.course=?',(ref,course)).fetchone()
            if e:result.append({'id':ref,'kind':e['kind'],'created':e['created']});continue
            m=self.db.execute('SELECT m.* FROM messages m JOIN sessions s ON s.id=m.session WHERE m.id=? AND s.course=?',(ref,course)).fetchone()
            if m:result.append({'id':ref,'kind':'message','text':m['text'],'created':m['created']})
        return result

    def course_cards(self,path,document=None,offset=0):
        self._path(path)
        rows=self.db.execute('SELECT DISTINCT u.document,u.card FROM course_units u WHERE u.path=? AND u.card IS NOT NULL AND (? IS NULL OR u.document=?) AND NOT EXISTS (SELECT 1 FROM passages p WHERE p.document=u.document AND p.reserved=1) ORDER BY u.document LIMIT 6 OFFSET ?',(path,document,document,max(0,int(offset)))).fetchall()
        return [{'document':r['document'],'card':unpack(r['card'])} for r in rows]

    def course_scope_material(self,sid,document,start=1,end=100):
        s=self.session(sid)
        row=self.db.execute('SELECT path FROM documents WHERE id=? AND course=?',(document,s['course'])).fetchone()
        if not row or not re.search(r'(?:plan|program|syllab|didatt|intro|inform|guide|schedule|timetable)',row[0].split('/')[-1],re.I) or is_exam(row[0]):raise ValueError('Prima di confermare i temi riservati si leggono solo programma e indicazioni introduttive; chiedi chiarimenti se mancano.')
        return self.read_material(sid,document,start,end)

    def course_coverage(self,path,document,offset=0):
        self._path(path)
        rows=self.db.execute('SELECT u.id,u.source,u.start,u.end,u.fingerprint,u.card IS NOT NULL done,p.page,p.start time_start,p.end time_end,p.quality FROM course_units u JOIN passages p ON p.id=u.source WHERE u.path=? AND u.document=? AND p.reserved=0 ORDER BY u.rowid LIMIT 50 OFFSET ?',(path,document,max(0,int(offset)))).fetchall()
        return [dict(r) for r in rows]

    def course_activity_states(self,sid):
        link=self._path_for_session(sid)
        if not link or self.session(sid)['mode']=='exam':return []
        rows=self.db.execute('SELECT a.id,a.version,a.state FROM activities a JOIN course_chapter_activities i ON i.activity=a.id AND i.activity_version=a.version WHERE i.session=? AND i.chapter=? AND i.version=?',(sid,link['chapter'],link['version'])).fetchall()
        return [dict(r,state=unpack(r['state'])) for r in rows]

    def course_progress(self,path):
        p=self._path(path);plan=self._plan(path)
        if not plan:return {}
        result={}
        for c in plan['data']['chapters']:
            rows=self.db.execute('SELECT a.*,v.spec FROM attempts a JOIN activities v ON v.id=a.activity AND v.version=a.version JOIN sessions s ON s.id=a.session WHERE s.course=? AND a.concept=? ORDER BY a.created',(p['course'],path+':'+c['id'])).fetchall()
            successes=[a for a in rows if unpack(a['grade']).get('correct') is True and not a['correction'] and unpack(a['spec']).get('kind')!='html']
            independent=[a for a in successes if not a['aids']]
            opened=bool(self.db.execute('SELECT 1 FROM course_chapter_exposure WHERE path=? AND chapter=?',(path,c['id'])).fetchone())
            state='affrontato' if opened or rows else 'da affrontare'
            if successes:state='riuscito con aiuti'
            if independent:state='riuscito autonomamente'
            from datetime import timedelta
            confirmed=[]
            for a in independent:
                for b in independent:
                    if datetime.fromisoformat(b['created'])-datetime.fromisoformat(a['created'])>=timedelta(days=1) and re.sub(r'\W+',' ',unpack(a['spec'])['prompt'].lower())!=re.sub(r'\W+',' ',unpack(b['spec'])['prompt'].lower()):confirmed=[a,b]
            if confirmed:state='riconfermato a distanza'
            evidence=confirmed or independent or successes
            result[c['id']]={'status':state,'attempts':len(rows),'aided':sum(bool(a['aids']) for a in successes),'autonomous':len(independent),'provisional':bool(evidence and any(unpack(a['grade']).get('status')!='verified' for a in evidence))}
        return result
