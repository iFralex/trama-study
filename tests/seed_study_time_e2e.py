"""Isolated browser fixture: two published chapters and one planned chapter; no personal archive."""
import argparse
import json
from pathlib import Path
from tests.seed_studio_e2e import seed as seed_base
from polimi_lectures.study import Study
from polimi_lectures.study_course import pack, stamp


def seed(root):
    result = seed_base(root)
    store = Study(Path(root));path = result['path'];plan = store._plan(path);data = plan['data']
    data['chapters'].append(dict(data['chapters'][-1], id='writing', title='Argomentazione e scrittura', objective='Interpretare un testo e costruire una tesi con esempi', assessment='Una risposta aperta motivata', exam_skills=['Interpretare', 'Argomentare', 'Rivedere un testo'], prerequisites=['reduction']))
    with store.db:
        store.db.execute('INSERT INTO course_plans VALUES(?,?,?,?,?)', (path, plan['version'] + 1, pack(data), 'Capitolo futuro della fixture', stamp()))
    for chapter in ['basics', 'reduction']:
        store._save_chapter(path, chapter, store._chapter(path, chapter)['content'])
    store.course_select(result['sid'], 'basics', version=store._chapter(path, 'basics')['version'])
    store.setting('last_course', result['course']);store.db.close()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('--root', required=True)
    print(json.dumps(seed(parser.parse_args().root)))
