"""Isolated complete v2 fixture. Never run on a personal data folder."""
import argparse,json,shutil
from pathlib import Path
from tests.seed_studio_e2e import seed
from tests.test_study_preparation import PreparationTest
from polimi_lectures.study import Study
from polimi_lectures.study_course import pack,stamp

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);args=parser.parse_args();root=Path(args.root)
    seed(root)
    course='selective-course-2026';shutil.copytree(root/'corsi'/'a-course-2025-26',root/'corsi'/course)
    (root/'corsi'/course/'lesson').rename(root/'corsi'/course/'2026-09-16_lezione')
    store=Study(root);store.import_course(course)
    fixture=PreparationTest();fixture.store=store;fixture.course=course;fixture.root=root
    chapter=fixture.to_chapter();fixture.commit(chapter,fixture.content())
    task=fixture.task();fixture.commit(task,{'solutions':[{'block':'exercise','answer':3,'reasoning':'Tre livelli'}]})
    for _ in range(2):task=fixture.task();fixture.commit(task,fixture.review(task))
    fixture.commit(fixture.task(),{});store.course_select(fixture.sid,'pram')
    with store.db:store.db.execute('INSERT INTO prep_issues VALUES(?,?,?,?,?,?,?)',(fixture.path,'notation-note','pram','intro','warning',pack({'message':'Confronta la notazione del docente con quella del testo.','sources':fixture.content()['blocks'][0]['sources']}),'open'))
    legacy=store.course_create(course,'Analisi storica da non riusare',reserved=[],engine=1)
    with store.db:store.db.execute('UPDATE course_paths SET objective=? WHERE id=?',(pack(dict(legacy['objective'],archived=True)),legacy['id']))
    store.setting('last_course',course);store.setting('model',{'provider':'fixture-unavailable','id':'none'})
    print(json.dumps({'root':str(root),'course':course,'path':fixture.path,'session':fixture.sid}));store.db.close()
if __name__=='__main__':main()
