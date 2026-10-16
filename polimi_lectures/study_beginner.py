"""Source-grounded beginner journeys. Navigation is distinct from learning evidence."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

PHASES=('foundations','explain','worked','guided','independent','recap')
PHASE_LABELS={'foundations':'Prerequisiti','explain':'Spiegazione','worked':'Esempio svolto','guided':'Prova guidata','independent':'Prova autonoma','recap':'Riepilogo','orientation':'Preparazione della lezione','recall':'Richiamo a distanza'}

def stamp():return datetime.now(timezone.utc).isoformat()

class BeginnerStudy:
    def setup_beginner(self):
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS beginner_sessions(session TEXT PRIMARY KEY,lesson TEXT);
          CREATE TABLE IF NOT EXISTS lesson_plans(session TEXT,lesson TEXT,units TEXT,unit INTEGER,phase TEXT,
            PRIMARY KEY(session,lesson));
          CREATE TABLE IF NOT EXISTS beginner_unit_positions(session TEXT,lesson TEXT,unit INTEGER,phase TEXT,PRIMARY KEY(session,lesson,unit));
          CREATE TABLE IF NOT EXISTS beginner_returns(session TEXT PRIMARY KEY,state TEXT);
          CREATE TABLE IF NOT EXISTS beginner_recalls(session TEXT,lesson TEXT,unit INTEGER,due TEXT,
            PRIMARY KEY(session,lesson,unit));
        ''')
        self.db.commit()

    def course_lessons(self, course):
        self.course_path(course)
        rows=self.db.execute("""SELECT d.id,d.path,MIN(p.quality) quality,MIN(p.start) start,MAX(p.end) end,COUNT(p.id) passages
          FROM documents d JOIN passages p ON p.document=d.id WHERE d.course=? AND d.issue IS NULL
          AND p.kind='video' AND p.reserved=0 GROUP BY d.id ORDER BY d.path""",(course,)).fetchall()
        rows=[dict(r,kind='video') for r in rows]
        known={str(Path(r['path']).parent.parent) for r in rows}
        for row in self.db.execute('''SELECT d.id,d.path,MIN(p.quality) quality,MIN(p.start) start,MAX(p.end) end,COUNT(p.id) passages
          FROM documents d JOIN passages p ON p.document=d.id WHERE d.course=? AND d.issue IS NULL AND p.kind='alignment'
          AND p.reserved=0 GROUP BY d.id ORDER BY d.path''',(course,)):
            if str(Path(row['path']).parent.parent) not in known:
                rows.append(dict(row,kind='alignment',quality='Trascrizione finale non disponibile · OCR e associazioni da verificare'))
        rows.sort(key=lambda r:r['path'])
        output=[]
        for row in rows:
            folder=Path(row['path']).parent.parent.name
            date=re.match(r'\d{4}-\d{2}-\d{2}',folder)
            time=re.search(r'_\d{2}-\d{2}-\d{4}-(\d{2})-(\d{2})',folder)
            label=(date[0] if date else folder[:70])+(' · '+':'.join(time.groups()) if time else '')
            label+=' · '+('Esercitazione' if 'esercitazione' in folder.casefold() else 'Lezione')
            output.append(dict(row,label=label,order=len(output)+1))
        if output:return output
        # With materials only, ordering is explicitly a file order, not invented chronology.
        rows=self.db.execute("""SELECT d.id,d.path,MIN(p.title) label,COUNT(p.id) passages FROM documents d
          JOIN passages p ON p.document=d.id WHERE d.course=? AND d.issue IS NULL AND p.kind IN ('pdf','notebook','text')
          AND p.reserved=0 AND p.solution=0 GROUP BY d.id""",(course,)).fetchall()
        rows=[r for r in rows if not re.search(r'(?:exams?|results?|\.sol\.|plan-didattica|syllabus|links)',r['path'],re.I)]
        def natural(row):return [int(t) if t.isdigit() else t.casefold() for t in re.split(r'(\d+)',row['path'])]
        for row in sorted(rows,key=natural):output.append(dict(row,order=len(output)+1,kind='material',quality='originale · ordine dei file, non cronologia verificata'))
        return output

    def _beginner_session(self,sid):
        s=self.session(sid)
        if s['mode']=='exam':raise ValueError('Percorso dalle basi escluso dalla simulazione.')
        journey=self.db.execute('SELECT lesson FROM beginner_sessions WHERE session=?',(sid,)).fetchone()
        if not journey:raise ValueError('Questa sessione non usa il percorso dalle basi.')
        return s,journey['lesson']

    def lesson_bundle(self,sid,lesson=None,offset=0,limit=25):
        session,current=self._beginner_session(sid)
        lesson=lesson or current
        catalog=self.course_lessons(session['course'])
        item=next((l for l in catalog if l['id']==lesson),None)
        if not item:raise ValueError('Lezione non disponibile nel corso corrente.')
        rows=self.db.execute("""SELECT p.* FROM passages p JOIN documents d ON d.id=p.document
          WHERE p.document=? AND d.issue IS NULL AND p.reserved=0 AND p.solution=0
          ORDER BY COALESCE(p.start,p.page),p.rowid""",(lesson,)).fetchall()
        linked=[];seen=set()
        if item['kind'] in ('video','alignment'):
            folder=str(Path(item['path']).parent.parent)+'/'
            alignments=self.db.execute("SELECT metadata,start,end FROM passages WHERE course=? AND kind='alignment' AND substr(path,1,?)=? ORDER BY start",(session['course'],len(folder),folder))
            for row in alignments:
                interval=json.loads(row['metadata']).get('alignment',{})
                material=interval.get('material') or interval.get('notebook')
                if not material:continue
                file=material.get('file');page=material.get('page',material.get('cell_index'))
                if not file:continue
                path=str(Path('corsi')/session['course']/'materiali'/file)
                for match in self.db.execute('SELECT id,title,page,quality FROM passages WHERE course=? AND path=? AND (? IS NULL OR page=?) AND solution=0 AND reserved=0',(session['course'],path,page,page)):
                    if match['id'] in seen:continue
                    seen.add(match['id']);linked.append(dict(match,status=interval.get('status','candidate'),confidence=interval.get('confidence'),start=row['start'],end=row['end']))
        def passage(row):
            result=dict(row,metadata=json.loads(row['metadata']))
            alignment=result['metadata'].get('alignment')
            if alignment:
                material=alignment.get('material') or alignment.get('notebook') or {}
                result['metadata']={'alignment':{'status':alignment.get('status'),'confidence':alignment.get('confidence'),
                  'material':{k:material[k] for k in ('file','page','cell_index','kind') if k in material}}}
            return result
        offset=max(0,int(offset));limit=max(1,min(int(limit),40))
        outline=[{'id':r['id'],'page':r['page'],'start':r['start'],'end':r['end'],'excerpt':r['text'][:180]} for r in rows]
        return {'lesson':item,'total_passages':len(rows),'offset':offset,
                'passages':[passage(r) for r in rows[offset:offset+limit]],
                'outline':outline,'linked_materials':linked,
                'notice':'Leggi i passaggi necessari e le slide originali. Una trascrizione parziale non dimostra copertura completa; un collegamento candidato non prova che una slide fosse visualizzata.'}

    def beginner_context(self,sid):
        row=self.db.execute('SELECT lesson FROM beginner_sessions WHERE session=?',(sid,)).fetchone()
        if not row:return None
        session=self.session(sid)
        lessons=self.course_lessons(session['course'])
        lesson=next((l for l in lessons if l['id']==row['lesson']),None)
        plan=self.db.execute('SELECT * FROM lesson_plans WHERE session=? AND lesson=?',(sid,row['lesson'])).fetchone()
        units=json.loads(plan['units']) if plan else []
        unit=plan['unit'] if plan else 0;phase=plan['phase'] if plan else 'orientation'
        recalls=[dict(r) for r in self.db.execute('SELECT lesson,unit,due FROM beginner_recalls WHERE session=? ORDER BY due',(sid,))]
        for recall in recalls:
            recall['lesson_label']=next((l['label'] for l in lessons if l['id']==recall['lesson']),'Lezione')
            saved=self.db.execute('SELECT units FROM lesson_plans WHERE session=? AND lesson=?',(sid,recall['lesson'])).fetchone()
            topics=json.loads(saved['units']) if saved else []
            recall['title']=topics[recall['unit']]['title'] if recall['unit']<len(topics) else 'Argomento'
        return {'approach':'beginner','lesson':lesson,'lessons':lessons,'units':units,'unit_index':unit,
                'current_unit':units[unit] if units and unit<len(units) else None,
                'phase':phase,'phase_label':PHASE_LABELS[phase],
                'at_end':bool(units and unit==len(units)-1 and phase=='recap' and lessons and lesson and lesson['id']==lessons[-1]['id']),
                'planned_lessons':self.db.execute('SELECT count(*) FROM lesson_plans WHERE session=?',(sid,)).fetchone()[0],
                'recalls':recalls,'navigation_is_not_mastery':True}

    def set_lesson_plan(self,sid,lesson,units):
        session,current=self._beginner_session(sid)
        if lesson!=current:raise ValueError('Prepara il piano della lezione corrente.')
        if not isinstance(units,list) or not 1<=len(units)<=30:raise ValueError('Servono da 1 a 30 argomenti con fonti.')
        prepared=[]
        for index,unit in enumerate(units):
            if not str(unit.get('title','')).strip() or not str(unit.get('objective','')).strip():raise ValueError('Titolo e obiettivo sono obbligatori.')
            refs=list(dict.fromkeys(unit.get('sources',[])))
            if not refs or len(refs)>12:raise ValueError('Ogni argomento deve avere fonti della lezione.')
            sources=[self.source(ref,allow_solutions=False) for ref in refs]
            if any(s['course']!=session['course'] for s in sources) or not any(s['document']==lesson for s in sources):
                raise ValueError('Ogni argomento deve essere ancorato alla lezione scelta, senza fonti di altri corsi.')
            prerequisites=unit.get('prerequisites',[])
            if not isinstance(prerequisites,list) or len(prerequisites)>12:raise ValueError('Prerequisiti non validi.')
            prepared.append({'id':lesson+':'+str(index),'title':str(unit['title'])[:180],
                             'objective':str(unit['objective'])[:700],
                             'prerequisites':[str(p)[:180] for p in prerequisites], 'sources':refs})
        existing=self.db.execute('SELECT units FROM lesson_plans WHERE session=? AND lesson=?',(sid,lesson)).fetchone()
        if existing:
            if json.loads(existing['units'])==prepared:return self.beginner_context(sid)
            raise ValueError('Il piano è già salvato: segui gli argomenti esistenti invece di ricrearlo a ogni messaggio.')
        with self.db:
            self.db.execute('INSERT INTO lesson_plans VALUES(?,?,?,?,?)',(sid,lesson,json.dumps(prepared,ensure_ascii=False),0,'foundations'))
        return self.beginner_context(sid)

    def _restore_beginner_return(self,sid):
        row=self.db.execute('SELECT state FROM beginner_returns WHERE session=?',(sid,)).fetchone()
        if not row:return False
        state=json.loads(row['state'])
        with self.db:
            for cursor in state['cursors']:
                self.db.execute('UPDATE lesson_plans SET unit=?,phase=? WHERE session=? AND lesson=?',(cursor['unit'],cursor['phase'],sid,cursor['lesson']))
            self.db.execute('UPDATE beginner_sessions SET lesson=? WHERE session=?',(state['lesson'],sid))
            self.db.execute('UPDATE sessions SET current=?,updated=? WHERE id=?',(state['current'],stamp(),sid))
            self.db.execute('DELETE FROM beginner_returns WHERE session=?',(sid,))
        return True

    def select_lesson(self,sid,lesson):
        session,_=self._beginner_session(sid)
        if lesson not in {l['id'] for l in self.course_lessons(session['course'])}:raise ValueError('Lezione non disponibile.')
        self._restore_beginner_return(sid)
        with self.db:
            self.db.execute('UPDATE beginner_sessions SET lesson=? WHERE session=?',(lesson,sid))
            self.db.execute('UPDATE sessions SET current=NULL,updated=? WHERE id=?',(stamp(),sid))
        return self.view(sid)

    def select_beginner_unit(self,sid,unit):
        self._beginner_session(sid)
        self._restore_beginner_return(sid)
        context=self.beginner_context(sid);unit=int(unit)
        if not 0<=unit<len(context['units']):raise ValueError('Argomento non disponibile nel piano della lezione.')
        lesson=context['lesson']['id']
        previous=self.db.execute('SELECT phase FROM beginner_unit_positions WHERE session=? AND lesson=? AND unit=?',(sid,lesson,unit)).fetchone()
        phase=context['phase'] if unit==context['unit_index'] else previous['phase'] if previous else 'foundations'
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO beginner_unit_positions VALUES(?,?,?,?)',(sid,lesson,context['unit_index'],context['phase']))
            self.db.execute('UPDATE lesson_plans SET unit=?,phase=? WHERE session=? AND lesson=?',(unit,phase,sid,lesson))
            self.db.execute('UPDATE sessions SET current=NULL,updated=? WHERE id=?',(stamp(),sid))
        return self.view(sid)

    def advance_beginner(self,sid):
        session,lesson=self._beginner_session(sid)
        context=self.beginner_context(sid)
        if not context['units']:return self.view(sid)
        unit=context['unit_index'];phase=context['phase']
        if phase=='independent':
            attempt=self.db.execute("""SELECT a.created FROM attempts a JOIN activities v ON v.id=a.activity AND v.version=a.version
              WHERE a.session=? AND json_extract(v.spec,'$.beginner.lesson')=? AND json_extract(v.spec,'$.beginner.unit')=?
              AND json_extract(v.spec,'$.beginner.phase')='independent' ORDER BY a.created DESC LIMIT 1""",(sid,lesson,unit)).fetchone()
            if attempt:
                from datetime import timedelta
                due=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
                with self.db:self.db.execute('INSERT OR IGNORE INTO beginner_recalls VALUES(?,?,?,?)',(sid,lesson,unit,due))
        if phase=='recall':
            submitted=self.db.execute("""SELECT 1 FROM attempts a JOIN activities v ON v.id=a.activity AND v.version=a.version
              WHERE a.session=? AND json_extract(v.spec,'$.beginner.lesson')=? AND json_extract(v.spec,'$.beginner.unit')=?
              AND json_extract(v.spec,'$.beginner.phase')='recall' LIMIT 1""",(sid,lesson,unit)).fetchone()
            if submitted:
                with self.db:self.db.execute('DELETE FROM beginner_recalls WHERE session=? AND lesson=? AND unit=?',(sid,lesson,unit))
            if self._restore_beginner_return(sid):return self.view(sid)
            phase='recap'
        elif phase!='recap':phase=PHASES[PHASES.index(phase)+1]
        elif unit+1<len(context['units']):unit+=1;phase='foundations'
        else:
            lessons=context['lessons'];index=next((i for i,l in enumerate(lessons) if l['id']==lesson),-1)
            if index+1<len(lessons):return self.select_lesson(sid,lessons[index+1]['id'])
            return self.view(sid)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO beginner_unit_positions VALUES(?,?,?,?)',(sid,lesson,context['unit_index'],context['phase']))
            self.db.execute('UPDATE lesson_plans SET unit=?,phase=? WHERE session=? AND lesson=?',(unit,phase,sid,lesson))
            self.db.execute('UPDATE sessions SET current=NULL,updated=? WHERE id=?',(stamp(),sid))
        return self.view(sid)

    def beginner_recall(self,sid,lesson,unit):
        session,current=self._beginner_session(sid)
        plan=self.db.execute('SELECT units FROM lesson_plans WHERE session=? AND lesson=?',(sid,lesson)).fetchone()
        if not plan or not 0<=int(unit)<len(json.loads(plan['units'])):raise ValueError('Argomento non disponibile.')
        self._restore_beginner_return(sid)
        current=self._beginner_session(sid)[1]
        cursors=[dict(r) for r in self.db.execute('SELECT lesson,unit,phase FROM lesson_plans WHERE session=? AND lesson IN (?,?)',(sid,lesson,current))]
        state={'lesson':current,'current':self.session(sid)['current'],'cursors':cursors}
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO beginner_returns VALUES(?,?)',(sid,json.dumps(state)))
            self.db.execute('UPDATE beginner_sessions SET lesson=? WHERE session=?',(lesson,sid))
            self.db.execute("UPDATE lesson_plans SET unit=?,phase='recall' WHERE session=? AND lesson=?",(int(unit),sid,lesson))
            self.db.execute('UPDATE sessions SET current=NULL,updated=? WHERE id=?',(stamp(),sid))
        return self.view(sid)
