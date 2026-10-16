import json
import re
import unicodedata
from pathlib import Path


def project_root():
    return Path(__file__).resolve().parent.parent


def load_config(project=None):
    path = (Path(project) if project else project_root()) / ".state" / "settings.json"
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Configurazione non valida: settings.json deve contenere un oggetto.")
    return value


def data_root(override=None, project=None):
    project = Path(project) if project else project_root()
    config = load_config(project)
    path = Path(override or config.get("data_dir") or project).expanduser().resolve()
    if not override and config.get("data_dir") and not path.is_dir():
        raise ValueError("La cartella dati configurata non è disponibile. Collega il disco o ripristina la cartella: %s" % path)
    parts = path.parts
    if len(parts) >= 3 and parts[1] == "Volumes":
        volume = Path(*parts[:3])
        if not volume.is_mount() and not volume.is_symlink():
            raise ValueError("Il disco dati non risulta montato: %s" % volume)
    return path


def course_key(label):
    """Identify a subject independently of academic year and lecturer."""
    label = re.sub(r'^\d+\s*-\s*', '', label)
    label = re.sub(r'\([^)]*\)', '', label)
    label = re.sub(r'\b20\d{2}(?:[-/]\d{2,4})?\b', '', label)
    label = unicodedata.normalize('NFKD', label).encode('ascii', 'ignore').decode().casefold()
    return ' '.join(re.findall(r'[a-z0-9]+', label))


def saved_course(preferences, query):
    choices = preferences.get('course_choices', {})
    exact = ' '.join(query.casefold().split())
    if exact in choices:
        return choices[exact]
    key = course_key(query)
    if key in choices:
        return choices[key]
    # Recover choices saved before subject aliases were introduced.
    for choice in reversed(list(choices.values())):
        if key and course_key(choice.get('label', '')) == key:
            return choice
    last = preferences.get('last_course', '')
    if key and course_key(last) == key:
        return {'label': last}
    return {}


def remember_course(label, url=None, query=None):
    project = project_root()
    config = load_config(project)
    config['last_course'] = label
    if url:
        choices = config.setdefault('course_choices', {})
        key = course_key(label)
        choice = {'label': label, 'url': url}
        for alias, previous in list(choices.items()):
            if course_key(previous.get('label', '')) == key:
                choices[alias] = choice
        for alias in (key, ' '.join(label.casefold().split()),
                      ' '.join((query or label).casefold().split())):
            if alias:
                choices[alias] = choice
    state = project / '.state'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = state / 'settings.json.tmp'
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(state / 'settings.json')
