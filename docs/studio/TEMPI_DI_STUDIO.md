# Stime locali del tempo di studio

Lo stimatore è generale: usa strutture del percorso e attività, senza identificatori di corsi, termini disciplinari o richieste al modello. Non apre documenti originali per stimarne la durata. I profili d'esame già salvati mantengono i normali controlli di provenienza. Tempi e marcature non vengono inseriti nei prompt, nel diario didattico, nelle valutazioni o nella certificazione del progresso.

## Primo studio, lavoro rimanente e richiami

Il primo studio comprende lettura ragionata, esempi, esercizi e lettura del riscontro. Per un capitolo disponibile si misurano testo visibile, formule inline e in blocco, righe di codice, immagini e attività. Soluzioni, rubriche, chiavi nascoste, script HTML e riferimenti bibliografici non sono volume di lettura. I laboratori usano il fallback testuale. È previsto un conteggio per caratteri per i sistemi di scrittura CJK.

I coefficienti iniziali sono ipotesi prudenziali di prodotto, non velocità scientificamente validate: 150 parole al minuto, tempo aggiuntivo per formule/codice e immagini, budget diversi per scelta, risposta numerica, completamento, risposta aperta e laboratorio, più revisione del feedback. Il risultato è sempre un intervallo. Per contenuti disponibili l'intervallo iniziale è 0,7–1,5 volte il calcolo centrale.

Per capitoli non ancora prodotti si usano obiettivo, progetto di valutazione, competenze e distribuzione dei formati d'esame già salvati. Il numero di riferimenti o pagine non equivale al tempo di studio. La densità di lettura e attività dei capitoli pubblicati affina la previsione nello stesso corso, con il peso di sei capitoli iniziali per evitare un'eccessiva estrapolazione dai primi esempi. Le previsioni dal programma mantengono un intervallo ampio (0,5–1,8). Alla pubblicazione vengono sostituite dal calcolo sul contenuto effettivo.

Il lavoro rimanente segue marcature esplicite per blocco: Studiato, Da rivedere, Da studiare. Scroll e cursore restano navigazione. Un tentativo consegnato riduce il lavoro di prima esecuzione, mantenendo tempo per il riscontro; un esito scorretto conserva anche un budget di nuovo tentativo. Le ore trascorse non sono sottratte dal rimanente. Una marcatura Studiato non modifica la valutazione o la competenza attribuita.

Il totale include tutti i capitoli del piano, compresi quelli futuri. I giorni di studio derivano dal ritmo quotidiano impostato per il percorso (quello dell'obiettivo o, inizialmente, 30 minuti modificabili). Sono giorni di impegno, non una previsione di data d'esame. I richiami già programmati hanno un budget separato, uno per card salvata: le ripetizioni future dipenderanno dalle risposte e non sono presentate come già note. Simulazioni e approfondimenti facoltativi fuori dai blocchi del percorso non sono aggiunti implicitamente.

## Tempo rilevato e calibrazione

La rilevazione locale conta finestre in primo piano, con pagina visibile e focus. È sospesa con tutor/fonti aperti, richieste in corso, richiami, schede in background e pausa esplicita. Dopo tre minuti senza interazioni la rilevazione si sospende; un'interazione o il comando di ripresa la riattiva. Si tratta di una proxy approssimativa: leggere fermi o ragionare lontano dal computer non è misurato con precisione.

Le finestre sono inviate ogni trenta secondi, ai cambi di blocco e alle pause. Il browser conserva gli intervalli non salvati e riprova senza chiamare modelli. Gli identificativi rendono i retry idempotenti. Una lease nel browser limita i timer concorrenti; il servizio unisce gli intervalli sovrapposti per corso, evitando doppio conteggio fra schede. Sleep del computer e salti dell'orologio separano le finestre e non diventano ore di studio fittizie. Ogni invio è limitato a sessanta secondi.

La calibrazione usa solamente blocchi esplicitamente marcati Studiato con tempo sufficiente e rapporto plausibile rispetto al calcolo iniziale. Ogni blocco conta come una osservazione, indipendentemente dal numero di heartbeat. Si usa una mediana con peso iniziale, almeno tre osservazioni per tipo di attività e fattori limitati. Le velocità sono separate per corso e tipo: i tempi di una materia non alterano automaticamente le altre.

Marcature e tempi sono associati all'impronta del blocco. Modifiche dei contenuti invalidano lo stato di quel blocco, preservando i precedenti; contenuti identici fra versioni mantengono la marcatura. Le versioni fissate nella lettura usano la loro stima, anche se è disponibile una revisione successiva. I dati persistono nel database SQLite, separati per percorso; il browser conserva pausa e invii ancora da salvare.

## Interfaccia e API

Il Percorso mostra totale, rimanente, giorni al ritmo scelto, richiami separati e tempi dei singoli capitoli. Il lettore mostra la stima del capitolo fuori dall'area di scorrimento, con dettagli, pausa del timer e marcature per sezione. L'indice comprende anche le previsioni dei capitoli da creare. I risultati si aggiornano al cambio di contenuti, marcature, tentativi o impostazioni; non a ogni tick del timer.

API browser dedicate:

- `GET /api/paths/:path/study-time`, con sessione e versione visibile facoltative.
- `POST /api/paths/:path/study-time`, per minuti giornalieri e rilevazione.
- `POST /api/sessions/:sid/study-time/mark`, per il lavoro affrontato.
- `POST /api/sessions/:sid/study-time/record`, per intervalli locali.

Il bridge valida appartenenza al percorso, versione e blocco, esclude registrazioni durante prove autonome e controlla intervalli, identificativi e sovrapposizioni. L'estimatore conserva una cache locale invalidata dagli input che usa. Le tabelle `study_time_marks`, `study_time_segments` e `study_time_options` sono create automaticamente senza modificare i dati esistenti.

## Verifiche

Il servizio è verificato con test su contenuti visibili, formule, codice, immagini e sistemi di scrittura diversi; capitoli futuri; passaggio da previsione a contenuto pubblicato; progressi espliciti; consegne; rilevazioni sovrapposte e retry; versioni fissate; impostazioni, richiami separati, calibrazione e corsi non tecnici. La cache viene verificata anche scambiando gli esiti di due tentativi, a parità di numero di errori. I test del timer coprono background, inattività, sleep e salti dell'orologio. Il test browser copre persistenza dopo ricaricamento, ritmo modificabile, capitoli ancora da creare e larghezza mobile.

La fixture riproducibile è `tests/seed_study_time_e2e.py`, da eseguire con il runtime nativo delle slide su una directory temporanea vuota. Avviare Studio su quella directory con porta 4327 e usare `STUDIO_TIME_E2E=1` per il test `studio/tests/e2e/study-time.spec.ts`. Il test verifica l'identità della fixture e non è attivo per impostazione predefinita sugli archivi personali.

Verifica dell'implementazione: suite TypeScript da 68 test passata; suite backend di corso/preparazione e prove specifiche dello stimatore passate, inclusi i 12 casi mirati finali; 11 test browser del nuovo pannello e dello spazio di studio passati; build riuscita. Nessuna richiesta al modello è necessaria per queste verifiche. Il controllo in sola lettura nell'app reale ha restituito correttamente tutte le 15 voci del percorso esistente, incluse le 13 ancora da creare: questi numeri sono un controllo sul campione, non parametri del calcolo.
