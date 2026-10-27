"""Start the local study UI, storing bulky tools on the configured data disk."""
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser

from .config import data_root, project_root


def main():
    os.umask(0o077)
    root=data_root()
    project=project_root()
    frontend=project/'studio'
    node=shutil.which('node')
    npm=shutil.which('npm')
    if not node or not npm:
        raise ValueError('Serve Node.js 22 o successivo. Installa Node.js, poi riapri Trama.')
    version=subprocess.check_output([node,'-p','process.versions.node'],text=True).strip()
    if int(version.split('.')[0])<22:
        raise ValueError('Serve Node.js 22 o successivo; versione rilevata: '+version)
    from .alignment import ensure_runtime
    python=asyncio.run(ensure_runtime(root))
    embedding_python=root/'.state/embeddings-runtime/bin/python'
    if not embedding_python.exists():
        print('Preparo gli embeddings locali sul disco dati…',flush=True)
        subprocess.run([str(python),'-m','venv',str(embedding_python.parent.parent)],check=True)
    embedding_stamp=root/'.state/embeddings-runtime/installed.version'
    if not embedding_stamp.exists() or embedding_stamp.read_text()!='fastembed==0.7.4':
        subprocess.run([str(embedding_python),'-m','pip','install','--cache-dir',str(root/'.state/pip-cache'),'fastembed==0.7.4'],check=True)
        embedding_stamp.write_text('fastembed==0.7.4')
    tools=root/'.state/studio-dependencies'
    tools.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256((frontend/'package-lock.json').read_bytes()).hexdigest()
    installed=tools/'installed.sha256'
    env=dict(os.environ,STUDIO_ROOT=str(root),STUDIO_PROJECT=str(project),STUDIO_PYTHON=str(python),PYTHONDONTWRITEBYTECODE='1',npm_config_cache=str(root/'.state/npm-cache'))
    if not installed.exists() or installed.read_text()!=digest:
        print('Preparo gli strumenti di Trama sul disco dati…',flush=True)
        for name in ('package.json','package-lock.json'):
            shutil.copy2(frontend/name,tools/name)
        subprocess.run([npm,'ci','--prefix',str(tools),'--no-audit','--no-fund'],env=env,check=True)
        installed.write_text(digest)
    modules=frontend/'node_modules'
    if modules.is_symlink() and modules.resolve()!=tools/'node_modules':
        modules.unlink()
    if not modules.exists():
        modules.symlink_to(tools/'node_modules',target_is_directory=True)
    stamp=root/'.state/studio-build.sha256'
    sources=sorted(p for p in frontend.rglob('*') if p.is_file() and not any(part in ('node_modules','dist','test-results') for part in p.relative_to(frontend).parts))
    source_digest=hashlib.sha256(b''.join(p.read_bytes() for p in sources)).hexdigest()
    if not (frontend/'dist/index.html').exists() or not stamp.exists() or stamp.read_text()!=source_digest:
        print('Preparo l’interfaccia di studio…',flush=True)
        subprocess.run([npm,'run','build'],cwd=frontend,env=env,check=True)
        stamp.write_text(source_digest)
    port=os.environ.get('STUDIO_PORT','4326')
    url='http://127.0.0.1:'+port
    try:
        with urllib.request.urlopen(url+'/api/bootstrap',timeout=1) as response:
            if 'courses' in json.load(response):
                webbrowser.open(url)
                print('Trama è già aperto: '+url)
                return 0
    except (OSError,ValueError):
        pass
    process=subprocess.Popen([str(modules/'.bin/tsx'),'server/index.ts'],cwd=frontend,env=env)
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise ValueError('Trama non è riuscito ad avviarsi. Controlla il messaggio nel terminale.')
            try:
                with urllib.request.urlopen(url+'/api/bootstrap',timeout=1):
                    break
            except OSError:
                time.sleep(.2)
        else:
            raise ValueError('Avvio non completato entro 20 secondi.')
        webbrowser.open(url)
        print('\nTrama è aperto nel browser. Lascia questo terminale aperto. Ctrl+C per fermarlo.\n',flush=True)
        return process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (OSError,ValueError,subprocess.CalledProcessError) as exc:
        print('Trama non avviato: '+str(exc),file=sys.stderr)
        raise SystemExit(1)
