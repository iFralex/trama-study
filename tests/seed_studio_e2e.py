"""Create an isolated browser fixture; never run against a personal archive."""
import argparse
import json
import shutil
from pathlib import Path
from tests.test_study import StudyTest
from polimi_lectures.study import Study


def seed(root):
    root=Path(root)
    if root.exists() and any(root.iterdir()):raise ValueError('Choose an empty test directory.')
    root.mkdir(parents=True,exist_ok=True)
    fixture=StudyTest();fixture.setUp()
    try:shutil.copytree(fixture.root/'corsi',root/'corsi')
    finally:fixture.tearDown()
    store=Study(root);store.import_course('a-course-2025-26')
    course='curriculum-fixture-2026';shutil.copytree(root/'corsi'/'a-course-2025-26',root/'corsi'/course)
    store.import_course(course)
    inventory=store.course_inventory(course);held=next(d['id'] for d in inventory['documents'] if d['title']=='PC-1st-part-25-07-21.pdf')
    p=store.course_create(course,engine=1,request='Primo parziale di test: PRAM',reserved=[held]);pid=p['id'];sid=p['sid']
    source=next(r[0] for r in store.db.execute("SELECT id FROM passages WHERE course=? AND title='lecture.pdf'",(course,)))
    task=store.course_task(pid);store.course_commit(pid,task,{'summary':'Primo parziale di test: PRAM','included':['PRAM','riduzione'],'excluded':['secondo parziale'],'clarification':None});store.course_confirm(pid)
    while True:
        task=store.course_task(pid)
        if task['kind']!='reading':break
        store.course_commit(pid,task,{'summary':'PRAM e riduzione','sources':[c['source'] for c in task['chunks']],'questions':[{'text':'Explain EREW and CREW.','format':'open','in_scope':True,'skills':['PRAM'],'sources':[task['chunks'][0]['source']],'points':1}] if task['exam'] else []})
    docs=[r[0] for r in store.db.execute('SELECT document FROM course_documents WHERE path=?',(pid,))]
    def chapter(cid,title,pre):return {'id':cid,'title':title,'objective':'Capire il modello e applicarlo','prerequisites':pre,'sources':[source],'priority':'alta','priority_reason':'Programma e quesiti d’esame','assessment':'Esempio svolto e variante autonoma','coverage':docs if not pre else []}
    blueprint={'chapters':[chapter('basics','PRAM dalle basi',[]),chapter('reduction','Riduzione parallela',['basics'])],'gaps':['Trascrizione parziale: confrontare con le slide.'],'outside_scope':[],'coverage_notes':'Copertura registrata per documento.'}
    while store.course_task(pid)['kind']=='integrate':store.course_commit(pid,store.course_task(pid),blueprint)
    store.course_commit(pid,store.course_task(pid),blueprint)
    for cid in ['basics','reduction']:
        blocks=[{'id':'foundations','kind':'text','text':'Un algoritmo è una sequenza di passi. Un processore esegue istruzioni. PRAM è un modello astratto con memoria condivisa. Il tempo $T(n)=an+b$ descrive un costo. [Slide](source:'+source+').','sources':[source]},
                {'id':'worked','kind':'text','text':'Esempio svolto: due processori leggono celle distinte nello stesso passo. Le letture sono esclusive.\n\n'+('Un esempio numerico commentato.\n\n'*30),'sources':[source]},
                {'id':'independent','kind':'activity','spec':{'kind':'numeric','title':'Riduzione: una variante autonoma','prompt':'Otto valori e processori sufficienti. Quanti livelli di somma servono?','answer':3,'solution':'Tre livelli: 8 → 4 → 2 → 1.','hints':['Ogni livello dimezza i valori.'],'rubric':'Distinguere valori e livelli','assumptions':'Una somma per passo, barriera tra livelli','origin':'generated','sources':[source]}}]
        store._save_chapter(pid,cid,{'blocks':blocks})
    store.course_select(sid,'basics');store.course_status(pid,'ready');store.setting('last_course','a-course-2025-26');store.db.close()
    return {'root':str(root),'course':course,'path':pid,'sid':sid,'source':source,'held':held}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);args=parser.parse_args();print(json.dumps(seed(args.root)))
