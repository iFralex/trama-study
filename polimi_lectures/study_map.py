"""Incremental course mapping: persist additions, reconcile once, keep original evidence."""
import copy
import math
import json
from .study_course import pack,unpack,stamp

STRATEGY='compact-map-1'
FACT_FIELDS=('id','concept','statement','notation','assumptions','examples','sources','issues','provenance','external_sources','notation_comparison')

def compact_fact(claim):
    return {key:claim[key] for key in FACT_FIELDS if key in claim}

def outline(plan):
    return [{key:chapter[key] for key in ('id','title','objective','prerequisites','priority','priority_reason','assessment','exam_skills') if key in chapter} for chapter in (plan or {}).get('data',{}).get('chapters',[])]

def recover_map_fields(text):
    """Recover only fully decoded values; never repair truncated strings/objects."""
    decoder=json.JSONDecoder();position=text.find('{')+1;fields={}
    if position<=0:return None
    while position<len(text):
        while position<len(text) and (text[position].isspace() or text[position]==','):position+=1
        try:
            key,position=decoder.raw_decode(text,position)
            while position<len(text) and text[position].isspace():position+=1
            if text[position]!=':':break
            position+=1
            while position<len(text) and text[position].isspace():position+=1
            value,end=decoder.raw_decode(text,position)
        except (ValueError,IndexError):break
        fields[key]=value;position=end
    if not isinstance(fields.get('chapters'),list) or not fields['chapters']:return None
    if not isinstance(fields.get('gaps'),list):return None
    return {k:fields[k] for k in ('chapters','gaps','outside_scope') if k in fields}

class MapStudy:
    def _map_setup(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS prep_map_builds(path TEXT,build TEXT,manifest TEXT,outline TEXT,created TEXT,PRIMARY KEY(path,build));
        CREATE TABLE IF NOT EXISTS prep_map_parts(path TEXT,build TEXT,part TEXT,task TEXT,data TEXT,PRIMARY KEY(path,build,part));
        CREATE TABLE IF NOT EXISTS prep_scope_changes(path TEXT,task TEXT,source TEXT,previous TEXT,current TEXT,PRIMARY KEY(task,source));
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
        review=self.db.execute('SELECT data FROM prep_map_reviews WHERE path=? AND version=?',(path,previous['version'])).fetchone() if previous else None
        feedback=unpack(review['data']) if review else (previous or {}).get('data',{}).get('review_feedback')
        if feedback and any(i.get('severity')=='blocking' for i in feedback.get('issues',[])):
            refs=list(dict.fromkeys(feedback.get('checked_sources',[])+[ref for issue in feedback.get('issues',[]) for ref in issue.get('sources',[])]))
            checked={r[0] for r in self.db.execute("SELECT r.source FROM prep_reads r JOIN prep_tasks t ON t.id=r.task WHERE t.path=? AND t.kind='map_review' AND json_extract(t.input,'$.plan.version')=?",(path,previous['version'] if review else previous['version']-1))}
            refs=[ref for ref in refs if ref in checked]
            originals=[self.source(ref,allow_solutions=False) for ref in refs]
            return self._prep_task(path,dict(base,kind='map',repair_version=1,repair_plan=previous,review_feedback=feedback,repair_sources=originals,final_batch=True,evidence_count=len(claims),covered=len(covered)))
        previous_notes={k:previous['data'][k] for k in ('gaps','outside_scope','coverage_notes','objective_coverage') if previous and k in previous['data']}
        return self._prep_task(path,dict(base,kind='map',reconciliation_version=2,recovery=self._map_recovery(path,build,claims),final_batch=True,outline=outline(previous) or chapters,previous_notes=previous_notes,contributions=[{'chapter':a['chapter'],'notes':a['notes'],'skills':a.get('skills',[])} for part in parts for a in part['additions']],review_feedback=(self._plan(path) or {}).get('data',{}).get('review_feedback'),selection=self._map_inventory(path),exam_profile=self._map_profile(path),evidence_count=len(claims),covered=len(covered)))

    def _map_recovery(self,path,build,claims):
        for row in self.db.execute("SELECT c.id,c.data,c.task,t.input FROM prep_model_calls c JOIN prep_tasks t ON t.id=c.task WHERE t.path=? AND t.kind='map' AND t.state='error' AND NOT EXISTS (SELECT 1 FROM prep_tasks newer WHERE newer.path=t.path AND newer.kind='map' AND newer.state='done' AND newer.rowid>t.rowid) ORDER BY c.rowid DESC LIMIT 3",(path,)):
            old=unpack(row['input'])
            if old.get('build')!=build or old.get('strategy')!=STRATEGY:continue
            fields=recover_map_fields(unpack(row['data']).get('output',''))
            if fields:
                allowed={ref for fact in claims for ref in fact.get('sources',[])}
                allowed.update(r[0] for r in self.db.execute('SELECT source FROM prep_reads WHERE task=?',(row['task'],)))
                refs={ref for chapter in fields['chapters'] for ref in chapter.get('sources',[])}
                if refs<=allowed:return {'call':row['id'],'fields':fields}
        return None

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
        if task.get('repair_version'):return self._map_apply_repair(path,task,result)
        # Keep earlier caveats without spending output tokens copying them. The
        # reconciler may explicitly refine an entry, but omission never erases it.
        if len(pack(result))>24000:raise ValueError('Riconciliazione troppo lunga: massimo 24000 caratteri prima delle bibliografie; sintetizza il progetto, non scrivere i capitoli.')
        data=copy.deepcopy(result)
        if task.get('recovery'):
            if any(k in data for k in ('chapters','gaps')):raise ValueError('La continuazione deve restituire solo i campi mancanti, senza riscrivere chapters o gaps recuperati.')
            recovered=copy.deepcopy(task['recovery']['fields'])
            recovered.update(data);data=recovered
            data['recovered_from_call']=task['recovery']['call']
        previous_notes=task.get('previous_notes',{})
        data['gaps']=list(dict.fromkeys(previous_notes.get('gaps',[])+data.get('gaps',[])))
        exclusions={e['document']:e for e in previous_notes.get('outside_scope',[])}
        exclusions.update({e['document']:e for e in data.get('outside_scope',[])})
        data['outside_scope']=list(exclusions.values())
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

    def _map_apply_repair(self,path,task,result):
        """Validated deltas preserve chapter identities and make retractions explicit."""
        current=self._plan(path)
        if not current or current['version']!=task['repair_plan']['version']:raise ValueError('Correzione obsoleta: il piano e cambiato.')
        if len(pack(result))>24000:raise ValueError('Correzioni troppo lunghe: massimo 24000 caratteri.')
        allowed={'chapter_updates','resolve_gaps','revoke_exclusions','scope_updates','gaps','outside_scope','coverage_notes','objective_coverage'}
        if set(result)-allowed:raise ValueError('Usa soltanto i campi della correzione mirata, non riscrivere il piano completo.')
        data=copy.deepcopy(current['data']);byid={c['id']:c for c in data['chapters']}
        refs={s['id'] for s in task['repair_sources']}
        def checked(values,required=False):
            if not isinstance(values,list) or any(not isinstance(v,str) for v in values):raise ValueError('Fonti della correzione non valide.')
            if required and not values:raise ValueError('La rettifica richiede le fonti originali verificate.')
            if not set(values)<=refs:raise ValueError('La correzione cita fonti non lette nella revisione: conserva i riferimenti forniti.')
            if values:self._refs(self._path(path)['course'],values,limit=None)
            return list(dict.fromkeys(values))
        for key in ('chapter_updates','resolve_gaps','revoke_exclusions','scope_updates','gaps','outside_scope'):
            if not isinstance(result.get(key,[]),list):raise ValueError('Campo '+key+' non valido.')
        seen=set()
        for change in result.get('chapter_updates',[]):
            cid=change.get('id')
            if cid not in byid or cid in seen:raise ValueError('Capitolo della correzione estraneo o duplicato.')
            seen.add(cid)
            if set(change)-{'id','objective','assessment','priority_reason','exam_skills','prerequisites','sources'}:raise ValueError('Campo del capitolo non modificabile dalla correzione.')
            chapter=byid[cid]
            for key in ('objective','assessment','priority_reason'):
                if key in change:
                    if not isinstance(change[key],str) or not change[key].strip():raise ValueError('Progetto del capitolo vuoto.')
                    chapter[key]=change[key]
            for key in ('exam_skills','prerequisites'):
                if key in change:
                    if not isinstance(change[key],list) or any(not isinstance(v,str) for v in change[key]):raise ValueError('Elenco del capitolo non valido.')
                    chapter[key]=change[key]
            additions=checked(change.get('sources',[]))
            chapter['sources']=sorted(set(chapter.get('sources',[]))|set(additions))
            chapter['coverage']=sorted(set(chapter.get('coverage',[]))|{self.source(ref,allow_solutions=False)['document'] for ref in additions})
        gaps=current['data'].get('gaps',[]);resolved=set();history=data.setdefault('gap_history',[])
        for decision in result.get('resolve_gaps',[]):
            index=decision.get('index')
            if type(index)!=int or not 0<=index<len(gaps) or index in resolved or not decision.get('reason'):raise ValueError('Lacuna da archiviare non valida o senza motivazione.')
            sources=checked(decision.get('sources',[]));resolved.add(index)
            history.append({'text':gaps[index],'reason':decision['reason'],'sources':sources,'state':'superseded','plan_version':current['version']})
        additions=result.get('gaps',[])
        if any(not isinstance(g,str) or not g.strip() for g in additions):raise ValueError('Nuove lacune non valide.')
        data['gaps']=list(dict.fromkeys([g for i,g in enumerate(gaps) if i not in resolved]+additions))
        exclusions={e['document']:e for e in data.get('outside_scope',[])};revoked=set()
        for decision in result.get('revoke_exclusions',[]):
            doc=decision.get('document')
            if doc not in exclusions or doc in revoked or not decision.get('reason'):raise ValueError('Esclusione da revocare non valida o senza motivazione.')
            sources=checked(decision.get('sources',[]),required=True)
            if not any(self.source(ref,allow_solutions=False)['document']==doc for ref in sources):raise ValueError('La revoca richiede una pagina verificata del documento.')
            revoked.add(doc);data.setdefault('scope_history',[]).append(dict(exclusions.pop(doc),state='revoked',reason_for_change=decision['reason'],sources=sources,plan_version=current['version']))
        for exclusion in result.get('outside_scope',[]):
            if not isinstance(exclusion,dict) or not exclusion.get('reason') or exclusion.get('document') in revoked:raise ValueError('Esclusione nuova non valida o gia revocata.')
            doc=exclusion.get('document')
            if not self.db.execute('SELECT 1 FROM passages WHERE course=? AND document=?',(self._path(path)['course'],doc)).fetchone():raise ValueError('Documento escluso estraneo al corso.')
            exclusions[doc]=exclusion
        data['outside_scope']=list(exclusions.values())
        for key in ('coverage_notes','objective_coverage'):
            if key in result:data[key]=result[key]
        scope_seen=set()
        for change in result.get('scope_updates',[]):
            ref=change.get('source');checked([ref],required=True)
            if ref in scope_seen or change.get('status') not in ('relevant','prerequisite') or not change.get('reason'):raise ValueError('Rettifica di selezione non valida.')
            if not self.db.execute('SELECT 1 FROM prep_spans WHERE path=? AND source=?',(path,ref)).fetchone():raise ValueError('Intervallo di selezione sconosciuto.')
            scope_seen.add(ref)
        # No source, goal, reservation or exposure is changed here. Scope updates
        # are committed transactionally only after all ordinary plan checks pass.
        data.pop('review_feedback',None);data['map_repair_version']=1
        data['repair_of_version']=current['version']
        return data

    def _map_commit_scope_repairs(self,path,task,result):
        for change in result.get('scope_updates',[]):
            ref=change['source'];row=self.db.execute('SELECT * FROM prep_spans WHERE path=? AND source=?',(path,ref)).fetchone()
            old=dict(row);new=dict(old,status=change['status'],reason=change['reason'],selected=1,done=1,cursor=len(self.source(ref,allow_solutions=False)['text']))
            self.db.execute('INSERT INTO prep_scope_changes VALUES(?,?,?,?,?)',(path,task['task_id'],ref,pack(old),pack(new)))
            self.db.execute('UPDATE prep_spans SET status=?,reason=?,selected=1,done=1,cursor=? WHERE path=? AND source=?',(new['status'],new['reason'],new['cursor'],path,ref))

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
