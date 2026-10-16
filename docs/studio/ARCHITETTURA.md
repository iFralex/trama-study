# Architettura e decisioni

React/Vite e assistant-ui rendono messaggi Markdown, formule e parti tool-call `study_activity`. Lo stesso componente didattico si usa nella chat e nel pannello ampio. Node/Express espone le API locali, esegue Pi e programma i richiami con ts-fsrs. Un processo Python persistente riceve richieste JSON-lines, accede agli originali in sola lettura e possiede SQLite. I processi esistenti per download, Whisper e allineamento conservano i loro ambienti.

## Confini

- `GET /api/bootstrap`, `POST /api/import`: corsi e indice incrementale.
- `POST /api/sessions`, `GET /api/sessions/:sid`: apertura/ripresa e snapshot.
- `POST /api/sessions/:sid/{next,select,preferences,recall}`: percorso, revisione selezionata, obiettivi e richiamo.
- `POST /api/sessions/:sid/events`: `{aid, version, event_id, kind, payload}`. Azioni: change, try, submit, hint, explain, solution, reset. Il backend attribuisce provenienza, aiuti e valutazione.
- `POST /api/sessions/:sid/chat`: stream SSE delta/done/error. Il testo utente viene salvato prima di contattare il provider; la risposta parziale viene conservata se interrotta.
- `POST /api/sessions/:sid/assess` e `/correct`: giudizio provvisorio e contestazione, senza cancellare il precedente.
- `GET /api/sessions/:sid/{search,sources/:id,media/:id,page/:id}`: ricerca, passaggi, file originali e rendering PDF; controlli su corso e modalità anche lato server.
- `/api/models`, `/api/model`, `/api/login`: catalogo, scelta e interazione con i provider Pi. Nessuna chiave passa nella cronologia didattica.

Pi dispone soltanto di search_sources, read_source, get_context e create_activity. Le spiegazioni citano ID effettivi con `[titolo](source:ID)`. Durante la simulazione il tutor conversazionale non viene eseguito. Il valutatore successivo non eredita la storia dello studio.

La preparazione della correzione verifica che il tentativo sia stato consegnato e appartenga alla sessione; aggiunge gli eventuali PDF `.sol.pdf` associati alle domande, conservando la distinzione tra domanda e soluzione. Questo accesso non viene esposto agli strumenti del tutor durante la prova. Anche usando una soluzione ufficiale, il giudizio linguistico rimane provvisorio.

## Artefatti

HTML inline in iframe `sandbox="allow-scripts"`, origine opaca, CSP senza rete. Il ponte `window.study.emit(kind,payload)` restituisce una Promise confermata dal parent dopo il salvataggio e invia eventi con token per istanza; il parent controlla finestra sorgente, token, azione e dimensione. I controlli con `data-key` salvano automaticamente il valore. L'evento `study:restore` ripristina lo stato custom. Un errore JavaScript mostra il fallback testuale.

Le chiavi delle attività strutturate restano sul server. L'HTML non può assegnare valutazioni, aggiornare competenze o eseguire RPC arbitrari. Le chiavi generate dal modello consentono feedback meccanico ma conservano stato provvisorio. Soltanto i controlli del percorso curato contribuiscono alle verifiche automatiche e ai richiami.

## Modello didattico

Il prossimo passo usa fonti, prerequisiti, tentativi, aiuti e richiami; lo studente può cambiare argomento o chiedere direttamente la soluzione. Il percorso iniziale ha esercizi verificati e attività generative aggiuntive. I giudizi aperti mantengono criteri e provenienza. FSRS programma i richiami brevi, senza trasformare il ricordo di un item in padronanza di un argomento.

Riferimenti progettuali: [Explorable Explanations](https://worrydream.com/ExplorableExplanations/), [PhET](https://phet.colorado.edu/en/teaching-resources/teaching-with-phet/small-group), [Quantum Country](https://andymatuschak.org/hmwl/), [Cognitive Tutors](https://www.cmu.edu/datalab/research/index.html), [assistant-ui](https://www.assistant-ui.com/docs/tools/generative-ui), [pi-artifacts](https://github.com/jakeryderv/pi-artifacts).

Il disegno distingue prestazione assistita e apprendimento autonomo, coerentemente con i risultati contestuali di [Kestin et al.](https://doi.org/10.1038/s41598-025-97652-6) e [Bastani et al.](https://doi.org/10.1073/pnas.2422633122). Nessuno dei due studi certifica l'efficacia di questa applicazione o un voto futuro.
