"""Incremental course mapping: persist additions, reconcile once, keep original evidence."""
import copy
import math
from .study_course import pack,unpack,stamp

STRATEGY='compact-map-1'
FACT_FIELDS=('id','concept','statement','notation','assumptions','examples','sources','issues','provenance','external_sources','notation_comparison')

def compact_fact(claim):
    return {key:claim[key] for key in FACT_FIELDS if key in claim}

def outline(plan):
    return [{key:chapter[key] for key in ('id','title','objective','prerequisites','priority','priority_reason','assessment','exam_skills') if key in chapter} for chapter in (plan or {}).get('data',{}).get('chapters',[])]

class MapStudy:
    def _map_setup(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS prep_map_builds(path TEXT,build TEXT,manifest TEXT,outline TEXT,created TEXT,PRIMARY KEY(path,build));
        CREATE TABLE IF NOT EXISTS prep_map_parts(path TEXT,build TEXT,part TEXT,task TEXT,data TEXT,PRIMARY KEY(path,build,part));
        """)

    def preparation_optimize_map(self,path):
        from .study_preparation import digest
        p=self._path(path)
        if not self._v2(path) or p['objective'].get('archived'):raise ValueError('Serve un percorso attivo del nuovo motore.')
        if p['status']=='running':raise ValueError('Metti in pausa la preparazione prima di ottimizzarla.')
        objective=dict(p['objective'],map_strategy=STRATEGY)
        with self.db:self.db.execute('UPDATE course_paths SET objective=?,error=NULL WHERE id=?',(pack(objective),path))
        return {'optimized':True,'strategy':STRATEGY}

    def _map_fingerprint(self,path,claims):
        from .study_preparation import digest
        return digest([STRATEGY,self._path(path)['objective'],[(compact_fact(c),c.get('dependencies'),c.get('access_fingerprints')) for c in claims]])

    def _map_state(self,path,claims):
        build=self._map_fingerprint(path,claims)
        row=self.db.execute('SELECT manifest,outline FROM prep_map_builds WHERE path=? AND build=?',(path,build)).fetchone()
        if row:return build,unpack(row['manifest']),unpack(row['outline'])
        base=self._plan(path);available={c['id']:c for c in claims};covered=set()
        # Reuse only completed mappings of THIS active run, with matching evidence.
        # Archived runs and unfinished model output cannot become a checkpoint.
        if base:
            for taskrow in self.db.execute("SELECT input FROM prep_tasks WHERE path=? AND kind='map' AND state='done'",(path,)):
                task=unpack(taskrow['input'])
                if task.get('strategy')==STRATEGY:continue
                if (task.get('previous') or {}).get('version',0)>=base['version']:continue
                for fact in task.get('evidence',[]):
                    current=available.get(fact.get('id'))
                    if current and compact_fact(fact)==compact_fact(current) and fact.get('dependencies')==current.get('dependencies') and fact.get('access_fingerprints')==current.get('access_fingerprints'):covered.add(current['id'])
        manifest={'base':base,'covered':sorted(covered),'all_ids':[c['id'] for c in claims]}
        initial=outline(base) or None
        if not getattr(self,'_peek_preparation',False):
            with self.db:self.db.execute('INSERT INTO prep_map_builds VALUES(?,?,?,?,?)',(path,build,pack(manifest),pack(initial),stamp()))
        return build,manifest,initial

    def _map_inventory(self,path):
        return [{'document':r['document'],'status':r['status'],'intervals':r['intervals'],'title':r['title'],'kind':r['kind']} for r in self.db.execute('SELECT p.document,s.status,count(*) intervals,min(p.title) title,min(p.kind) kind FROM prep_spans s JOIN passages p ON p.id=s.source WHERE s.path=? GROUP BY p.document,s.status',(path,))]

    def _map_task(self,path,claims,common):
        from .study_preparation import digest
        build,manifest,chapters=self._map_state(path,claims)
        # Budget belongs to the actual model; bookkeeping and original excerpts stay in SQLite.
        base=dict(common,strategy=STRATEGY,build=build)
        if not chapters:
            return self._prep_task(path,dict(base,kind='map_outline',concepts=list(dict.fromkeys(c['concept'] for c in claims)),selection=self._map_inventory(path),exam_profile=self._map_profile(path)))
        parts=[unpack(r[0]) for r in self.db.execute('SELECT data FROM prep_map_parts WHERE path=? AND build=? ORDER BY rowid',(path,build))]
        covered=set(manifest['covered'])|{cid for part in parts for addition in part['additions'] for cid in addition['evidence']}
        remaining=[c for c in claims if c['id'] not in covered]
        if remaining:
            # At most 32k estimated source tokens, while leaving room for objective and outline.
            compact_outline=[{k:c[k] for k in ('id','title','objective','prerequisites') if k in c} for c in chapters]
            overhead=math.ceil(len(pack({'outline':compact_outline,'objective':self._path(path)['objective']}))/3)+2000
            budget=max(1000,common['budget']-overhead);batch=[];used=0
            for claim in remaining:
                fact=compact_fact(claim);cost=math.ceil(len(pack(fact))/3)
                if batch and used+cost>budget:break
                batch.append(fact);used+=cost
            return self._prep_task(path,dict(base,kind='map_contribution',part=digest([c['id'] for c in batch]),outline=compact_outline,evidence=batch,evidence_ids=[c['id'] for c in batch],covered=len(covered),total=len(claims)))
        previous=self._plan(path)
        previous_notes={k:previous['data'][k] for k in ('gaps','outside_scope','coverage_notes','objective_coverage') if previous and k in previous['data']}
        return self._prep_task(path,dict(base,kind='map',final_batch=True,outline=outline(previous) or chapters,previous_notes=previous_notes,contributions=[{'chapter':a['chapter'],'notes':a['notes'],'skills':a.get('skills',[])} for part in parts for a in part['additions']],review_feedback=(self._plan(path) or {}).get('data',{}).get('review_feedback'),selection=self._map_inventory(path),exam_profile=self._map_profile(path),evidence_count=len(claims),covered=len(covered)))

    def _map_profile(self,path):
        profile=self.course_exam_profile(path)
        return {k:profile[k] for k in ('total','excluded_total','formats','skills','sample_size','limitations')}

    def _map_outline_validate(self,chapters):
        if not isinstance(chapters,list) or not 1<=len(chapters)<=80:raise ValueError('L’indice deve contenere da 1 a 80 capitoli.')
        seen=set()
        for c in chapters:
            cid=c.get('id')
            if not isinstance(cid,str) or not cid or len(cid)>100 or cid in seen:raise ValueError('ID del capitolo non valido o duplicato.')
            if any(not isinstance(c.get(k),str) or not c[k].strip() for k in ('title','objective','priority_reason','assessment')):raise ValueError('Capitolo senza progetto didattico.')
            if not isinstance(c.get('prerequisites',[]),list) or not set(c.get('prerequisites',[]))<=seen:raise ValueError('Prerequisiti mancanti o ciclici.')
            seen.add(cid)
        if len(pack(chapters))>40000:raise ValueError('Indice troppo lungo: conserva obiettivi e prerequisiti, non scrivere i capitoli.')

    def _map_commit_part(self,path,task,result):
        if self._map_fingerprint(path,self.preparation_evidence(path,limit=100000))!=task['build']:raise ValueError('Evidenze o obiettivo cambiati: contributo obsoleto rifiutato.')
        if task['kind']=='map_outline':
            chapters=outline({'data':{'chapters':result.get('chapters',[])}});self._map_outline_validate(chapters)
            with self.db:self.db.execute('UPDATE prep_map_builds SET outline=? WHERE path=? AND build=?',(pack(chapters),path,task['build']))
            return
        additions=result.get('additions');expected=set(task['evidence_ids']);seen=set();valid={c['id'] for c in task['outline']}
        if not isinstance(additions,list) or not additions:raise ValueError('Servono contributi per tutte le evidenze proposte.')
        for addition in additions:
            ids=addition.get('evidence')
            if addition.get('chapter') not in valid:raise ValueError('Capitolo non presente nell’indice. Segnala la lacuna in notes senza inventare ID.')
            if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)) or not set(ids)<=expected:raise ValueError('Il contributo cita evidenze estranee, duplicate o mancanti.')
            if not isinstance(addition.get('notes'),str) or not 1<=len(addition['notes'])<=2000:raise ValueError('Ogni contributo richiede notes tra 1 e 2000 caratteri.')
            if not isinstance(addition.get('skills',[]),list) or any(not isinstance(v,str) for v in addition.get('skills',[])):raise ValueError('Competenze non valide.')
            seen.update(ids)
        if seen!=expected:raise ValueError('Mancano contributi per le evidenze: '+', '.join(sorted(expected-seen)))
        if len(pack(result))>40000:raise ValueError('Contributi troppo lunghi: sintetizza senza ricopiare gli originali.')
        with self.db:self.db.execute('INSERT INTO prep_map_parts VALUES(?,?,?,?,?)',(path,task['build'],task['part'],task['task_id'],pack(result)))

    def _map_merge(self,path,task,result):
        from .study_preparation import digest
        claims=self.preparation_evidence(path,limit=100000)
        if self._map_fingerprint(path,claims)!=task['build']:raise ValueError('Evidenze o obiettivo cambiati: riconciliazione obsoleta.')
        build,manifest,chapters=self._map_state(path,claims)
        if build!=task['build']:raise ValueError('Evidenze o obiettivo cambiati: usa i contributi compatibili del nuovo compito.')
        parts=[unpack(r[0]) for r in self.db.execute('SELECT data FROM prep_map_parts WHERE path=? AND build=?',(path,build))]
        covered=set(manifest['covered'])|{cid for part in parts for a in part['additions'] for cid in a['evidence']}
        if covered!=set(manifest['all_ids']):raise ValueError('La mappa non copre tutte le evidenze analizzate.')
        pool={c['id']:{'sources':set(c.get('sources',[])),'coverage':set(c.get('coverage',[]))} for c in (manifest['base'] or {}).get('data',{}).get('chapters',[])}
        byid={c['id']:c for c in claims}
        for part in parts:
            for a in part['additions']:
                chapter=pool.setdefault(a['chapter'],{'sources':set(),'coverage':set()})
                for cid in a['evidence']:
                    for ref in byid[cid]['sources']:
                        chapter['sources'].add(ref);chapter['coverage'].add(self.source(ref,allow_solutions=False)['document'])
        data=copy.deepcopy(result)
        ids={c['id'] for c in data.get('chapters',[])}
        if not {c['id'] for c in chapters}<=ids:raise ValueError('Conserva tutti i capitoli dell’indice e i relativi contributi.')
        selected_documents={r[0] for r in self.db.execute("SELECT DISTINCT p.document FROM prep_spans s JOIN passages p ON p.id=s.source WHERE s.path=? AND s.status!='outside'",(path,))}
        for c in data.get('chapters',[]):
            if not isinstance(c.get('coverage',[]),list) or not set(c.get('coverage',[]))<=selected_documents:raise ValueError('Copertura del capitolo con documenti estranei o fuori perimetro.')
            bibliography=pool.get(c['id'],{'sources':set(),'coverage':set()})
            c['sources']=sorted(set(c.get('sources',[]))|bibliography['sources'])
            c['coverage']=sorted(set(c.get('coverage',[]))|bibliography['coverage'])
        data['map_build']=build
        return data

    def _map_context(self,path,claims,chapter=None):
        """Small source-grounded context for review/teaching; originals stay available via tools."""
        plan=self._plan(path);build=(plan or {}).get('data',{}).get('map_build')
        parts=[unpack(r[0]) for r in self.db.execute('SELECT data FROM prep_map_parts WHERE path=? AND build=?',(path,build))] if build else []
        if chapter:
            refs=set(chapter.get('sources',[]));claims=[c for c in claims if refs.intersection(c['sources'])]
        return {'concepts':list(dict.fromkeys(c['concept'] for c in claims)),'contributions':[a for part in parts for a in part['additions'] if not chapter or a['chapter']==chapter['id']],'total_evidence':len(claims),'retrieval':'Use read_preparation_evidence to retrieve full semantic evidence by ID or chapter. Original sources remain accessible.'}

    def preparation_facts(self,path,ids=None,chapter=None,offset=0,limit=30):
        claims=self.preparation_evidence(path,limit=100000)
        if ids is not None:
            if not isinstance(ids,list) or len(ids)>100:raise ValueError('Richiedi al massimo 100 evidenze per volta.')
            available={c['id'] for c in claims}
            if not set(ids)<=available:raise ValueError('Evidenza non disponibile in questo percorso.')
            claims=[c for c in claims if c['id'] in ids]
        if chapter:
            plan=self._plan(path);c=next((c for c in (plan or {}).get('data',{}).get('chapters',[]) if c['id']==chapter),None)
            if not c:raise ValueError('Capitolo non disponibile.')
            refs=set(c['sources']);claims=[c for c in claims if refs.intersection(c['sources'])]
        start=max(0,int(offset));limit=max(1,min(100,int(limit)))
        return {'evidence':[compact_fact(c) for c in claims[start:start+limit]],'total':len(claims),'offset':start,'next_offset':start+limit if start+limit<len(claims) else None}
