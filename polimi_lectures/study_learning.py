"""Conversation-local drafts with safe continuity of equivalent curriculum exercises.

Original attempts/events are never copied or renumbered. Browser views bind them
only to the identical exercise, chapter version and study path in a new conversation.
"""
import copy
import json


class LearningContinuity:
    def _course_activity_peers(self, sid, activity):
        session = self.session(sid);spec = activity['spec']
        if session['mode'] != 'learn' or spec.get('curriculum', {}).get('recall'):
            return []
        binding = self.db.execute('''SELECT p.path,i.chapter,i.version,i.block FROM course_chapter_activities i
          JOIN course_path_sessions p ON p.session=i.session
          WHERE i.session=? AND i.activity=? AND i.activity_version=? LIMIT 1''', (sid, activity['id'], activity['version'])).fetchone()
        if not binding:return []
        peers = []
        for row in self.db.execute('''SELECT DISTINCT a.* FROM activities a
          JOIN course_chapter_activities i ON i.activity=a.id AND i.activity_version=a.version
          JOIN course_path_sessions p ON p.session=i.session JOIN sessions s ON s.id=a.session
          WHERE p.path=? AND i.chapter=? AND i.version=? AND i.block=? AND s.mode='learn' AND s.course=?''', (*tuple(binding), session['course'])):
            stored = json.loads(row['spec'])
            if stored == spec and not stored.get('curriculum', {}).get('recall'):
                peers.append(dict(row, spec=stored, state=json.loads(row['state'])))
        return peers

    def _course_inherited_state(self, sid, activity, peers=None):
        if activity['state'] or self.db.execute("SELECT 1 FROM events WHERE session=? AND activity=? AND version=? AND kind IN ('change','try','reset','submit') LIMIT 1", (sid, activity['id'], activity['version'])).fetchone():
            return activity['state']
        candidates = []
        for peer in peers if peers is not None else self._course_activity_peers(sid, activity):
            if peer['id'] == activity['id'] and peer['version'] == activity['version']:continue
            event = self.db.execute("SELECT kind,payload,created FROM events WHERE session=? AND activity=? AND version=? AND kind IN ('change','try','reset','submit') ORDER BY rowid DESC LIMIT 1", (peer['session'], peer['id'], peer['version'])).fetchone()
            if not event and not peer['state']:continue
            state = copy.deepcopy(peer['state'])
            if event and event['kind'] == 'reset':state = {}
            elif event and event['kind'] == 'submit':
                payload = json.loads(event['payload'])
                if 'answer' in payload:state['answer'] = payload['answer']
            candidates.append((event['created'] if event else peer['created'], state))
        return max(candidates, key=lambda item:item[0])[1] if candidates else activity['state']

    def course_learning_view(self, sid, result):
        if not self._path_for_session(sid) or result['session']['mode'] != 'learn':return result
        attempts = {a['id']:a for a in result['attempts']}
        for public in result['activities']:
            row = self.db.execute('SELECT * FROM activities WHERE session=? AND id=? AND version=?', (sid, public['id'], public['version'])).fetchone()
            activity = dict(row, spec=json.loads(row['spec']), state=json.loads(row['state']))
            peers = self._course_activity_peers(sid, activity)
            public['state'] = self._course_inherited_state(sid, activity, peers)
            for peer in peers:
                for raw in self.db.execute('SELECT *,rowid ordinal FROM attempts WHERE session=? AND activity=? AND version=? ORDER BY rowid', (peer['session'], peer['id'], peer['version'])):
                    if raw['id'] in attempts:continue
                    attempts[raw['id']] = dict(raw, activity=public['id'], version=public['version'], answer=json.loads(raw['answer']), grade=json.loads(raw['grade']), source_session=raw['session'], source_activity=raw['activity'], source_version=raw['version'])
        result['attempts'] = sorted(attempts.values(), key=lambda a:(a['created'], a.get('ordinal', 0)))
        return result

    def course_attempt_session(self, sid, attempt_id):
        """Resolve a historical attempt only if the caller owns an exact curriculum equivalent."""
        attempt = self.db.execute('SELECT * FROM attempts WHERE id=?', (attempt_id,)).fetchone()
        if not attempt:return None
        if attempt['session'] == sid:return sid
        caller = self.session(sid);owner = self.session(attempt['session'])
        link = self._path_for_session(sid);origin = self._path_for_session(attempt['session'])
        if not link or not origin or link['path'] != origin['path'] or caller['mode'] != 'learn' or owner['mode'] != 'learn' or caller['course'] != owner['course']:
            return None
        binding = self.db.execute('SELECT chapter,version,block FROM course_chapter_activities WHERE session=? AND activity=? AND activity_version=? LIMIT 1', (attempt['session'], attempt['activity'], attempt['version'])).fetchone()
        if not binding:return None
        target = self.db.execute('''SELECT a.* FROM activities a JOIN course_chapter_activities i ON i.activity=a.id AND i.activity_version=a.version
          WHERE i.session=? AND i.chapter=? AND i.version=? AND i.block=? LIMIT 1''', (sid, *tuple(binding))).fetchone()
        if not target:return None
        activity = dict(target, spec=json.loads(target['spec']), state=json.loads(target['state']))
        return attempt['session'] if any(p['id'] == attempt['activity'] and p['version'] == attempt['version'] and p['session'] == attempt['session'] for p in self._course_activity_peers(sid, activity)) else None

    def course_learning_aids(self, sid, activity, hint_only=False):
        peers = self._course_activity_peers(sid, activity)
        kinds = "('hint')" if hint_only else "('hint','explain','solution')"
        if not peers:
            return self.db.execute('SELECT count(*) FROM events WHERE session=? AND activity=? AND kind IN '+kinds, (sid, activity['id'])).fetchone()[0]
        return sum(self.db.execute('SELECT count(*) FROM events WHERE session=? AND activity=? AND version=? AND kind IN '+kinds, (p['session'], p['id'], p['version'])).fetchone()[0] for p in peers)
