"""Configurazione iniziale e copia verificata dell'archivio, senza eliminare l'originale."""
import json
import os
import re
import shlex
import shutil
import sqlite3
import tempfile
from pathlib import Path

from .config import data_root, load_config, project_root


class ConfigurationError(Exception):
    pass


def parse_folder(value):
    value = value.strip()
    # Accetta anche il percorso trascinato da Finder (quotato o con spazi escapati).
    if value.startswith(("'", '"')) or "\\" in value:
        try:
            parts = shlex.split(value)
            if len(parts) == 1:
                value = parts[0]
        except ValueError:
            pass
    return Path(value).expanduser().resolve()


def validate_destination(destination):
    parts = destination.parts
    if len(parts) >= 3 and parts[1] == "Volumes":
        volume = Path(*parts[:3])
        if not volume.is_mount() and not volume.is_symlink():
            raise ConfigurationError("Il disco %s non risulta montato. Collegalo e riprova." % volume)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".polimi-write-test-", dir=str(destination)):
        pass


def browser_running(source):
    lock = source / ".state" / "browser" / "SingletonLock"
    if lock.is_symlink():
        try:
            pid = int(os.readlink(str(lock)).rsplit("-", 1)[-1])
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except (OSError, ValueError):
            return True
    return lock.exists()


def ignored(directory, names):
    skip = {"SingletonLock", "SingletonCookie", "SingletonSocket", "Cache", "Code Cache", "GPUCache"}
    if Path(directory).name == ".state":
        skip |= {"browser", "browsers", "pip-cache", "settings.json", "auth-state.json", "auth-state.json.tmp"}
    return set(names) & skip


def tree_bytes(source):
    total = 0
    for directory, dirs, files in os.walk(str(source)):
        excluded = ignored(directory, dirs + files)
        dirs[:] = [name for name in dirs if name not in excluded]
        for name in files:
            path = Path(directory) / name
            if name not in excluded and not path.is_symlink():
                total += path.stat().st_size
    return total


def catalog_entries(path):
    if not path.exists():
        return []
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        return db.execute("SELECT course,id,title,date,status,path,error FROM lessons ORDER BY course,id").fetchall()


def copy_archive(source, destination, profile_root=None):
    source, destination = source.resolve(), destination.resolve()
    if source == destination:
        return False
    for name in (".state", "corsi", "modelli"):
        if destination == source / name or (source / name) in destination.parents:
            raise ConfigurationError("Scegli una cartella esterna alle directory .state, corsi e modelli dell'archivio corrente.")
    pieces = [name for name in (".state", "corsi", "modelli") if (source / name).is_dir()]
    # Una nuova installazione con soli settings/browser binari non ha dati da migrare.
    if not (source / ".state" / "catalog.sqlite3").exists() and not (source / "corsi").exists() and not (source / ".state" / "debug-html").exists() and not (source / "modelli").exists() and not (source / ".state/whisper").exists():
        return False
    if browser_running(profile_root or source):
        raise ConfigurationError("Chiudi il browser del downloader e termina Avvia.command prima di cambiare cartella dati.")
    for name in pieces:
        if (destination / name).exists():
            raise ConfigurationError("La destinazione contiene già %s. Scegli una cartella vuota per evitare sovrascritture." % name)
    required = sum(tree_bytes(source / name) for name in pieces)
    if shutil.disk_usage(str(destination)).free < required + 64 * 1024 * 1024:
        raise ConfigurationError("Spazio insufficiente nella destinazione per copiare l'archivio esistente.")
    staging = Path(tempfile.mkdtemp(prefix=".polimi-migration-", dir=str(destination)))
    try:
        print("Copia dell'archivio esistente (%.1f MB)…" % (required / 1_000_000), flush=True)
        for name in pieces:
            shutil.copytree(source / name, staging / name, ignore=ignored, symlinks=True)
        old_db = source / ".state" / "catalog.sqlite3"
        new_db = staging / ".state" / "catalog.sqlite3"
        if old_db.exists():
            # Usa SQLite backup per includere correttamente eventuali journal/WAL.
            new_db.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm", "-journal"):
                Path(str(new_db) + suffix).unlink(missing_ok=True)
            with sqlite3.connect(old_db.as_uri() + "?mode=ro", uri=True) as old:
                with sqlite3.connect(str(new_db)) as new:
                    old.backup(new)
            new_db.chmod(0o600)
            if catalog_entries(old_db) != catalog_entries(new_db):
                raise ConfigurationError("Verifica del catalogo copiato fallita: configurazione non cambiata.")
        whisper_settings = staging / '.state/whisper/settings.json'
        if whisper_settings.exists():
            whisper = json.loads(whisper_settings.read_text(encoding='utf-8'))
            if whisper.get('model'):
                try:
                    relative = Path(whisper['model']).resolve().relative_to(source)
                except ValueError:
                    pass
                else:
                    if relative.parts and relative.parts[0] == 'modelli' and (staging / relative).is_file():
                        whisper['model'] = str(destination / relative)
                        whisper_settings.write_text(json.dumps(whisper, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for name in pieces:
            (staging / name).rename(destination / name)
        if (destination / ".state").exists():
            (destination / ".state").chmod(0o700)
        return True
    finally:
        shutil.rmtree(staging)


def configure(project, email, destination):
    email = email.strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ConfigurationError("Inserisci un indirizzo email valido.")
    project = Path(project).resolve()
    config = load_config(project)
    previous = data_root(project=project)
    destination = Path(destination).expanduser().resolve()
    validate_destination(destination)
    copied = copy_archive(previous, destination, profile_root=project)
    config.update(email=email, data_dir=str(destination))
    config.setdefault("debug_html", True)
    state = project / ".state"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    temp = state / "settings.json.tmp"
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(state / "settings.json")
    return copied


def main():
    os.umask(0o077)
    project = project_root()
    try:
        config = load_config(project)
        default_email = config.get("email", "")
        default_dir = data_root(project=project)
        print("Configurazione Polimi Lectures. Invio mantiene un valore già configurato.")
        email = input("Email Webex/Polimi%s: " % (" [%s]" % default_email if default_email else "")).strip() or default_email
        folder = input("Cartella dati [%s]: " % default_dir).strip()
        destination = parse_folder(folder) if folder else default_dir
        copied = configure(project, email, destination)
        print("Email: %s\nCartella dati: %s" % (email, destination))
        print("Spazio libero nella destinazione: %.1f GB" % (shutil.disk_usage(str(destination)).free / 1_000_000_000))
        if copied:
            print("Archivio copiato e catalogo verificato. Gli originali restano nella vecchia cartella.")
        print("Configurazione salvata.")
        return 0
    except (ConfigurationError, OSError, ValueError) as exc:
        print("Configurazione non completata: %s" % exc)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nConfigurazione annullata.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
