# Preparazione dalle fonti originali — motore 2

La preparazione seleziona fonti e intervalli in funzione dell’esame. Una fonte elaborata non è una competenza acquisita; un capitolo revisionato dall’AI non è una garanzia di correttezza assoluta.

## Archivio e ripartenza

**Archivia e riparti dalle fonti originali** conserva il percorso precedente, le sue schede, conversazioni e tentativi. Il nuovo percorso eredita soltanto la richiesta originale dello studente, data/minuti e temi scelti esplicitamente come simulazioni. Non eredita sintesi, piani, capitoli o valutazioni AI. Il vecchio percorso è contrassegnato come archivio e non può riprendere la preparazione.

Il provider è quello configurato in Pi. Nessuna nuova autenticazione è richiesta. Il perimetro rigenerato si rivede nella scheda prima della lettura approfondita. La selezione successiva delle fonti è automatica e correggibile.

## Sequenza

1. Ricognizione e scheda del perimetro, usando metadati e indicazioni introduttive.
2. Protezione locale delle simulazioni prima dell’analisi del corpus.
3. Lettura dei temi autentici disponibili, con distinzione fra primo/secondo parziale e prova completa.
4. Selezione di pagine, celle e intervalli: pertinente, prerequisito, fuori perimetro, da verificare. Estratti insufficienti rimangono incerti e richiedono lettura completa.
5. Lettura delle fonti selezionate per unità coerenti, con slide/celle collegate alla trascrizione. Gli allineamenti sono relazioni strutturate, non ulteriori documenti da riassumere.
6. Estrazione di nuove evidenze separate: concetto, affermazione, ipotesi, notazione, esempi, fonti e problemi. Nessun riassunto cumulativo riscritto a ogni richiesta.
7. Integrazione progressiva nella mappa, controllo di copertura degli obiettivi, prerequisiti e fonti selezionate, quindi revisione della mappa.
8. Produzione del capitolo corrente e del successivo. Risoluzione indipendente degli esercizi senza chiavi dell’autore, revisione disciplinare e revisione didattica complete, eventuale correzione e nuova revisione, pubblicazione.

I capitoli restanti conservano il progetto didattico e vengono sviluppati quando ci si avvicina allo studio. Il percorso può adattarsi alle evidenze personali mantenendo versioni e possibilità di ripristino.

## Evidenze e fonti

Ogni lettura iniziale o eseguita con strumenti registra testo effettivamente restituito, intervallo, impronta della fonte e metodo. Un risultato di ricerca non costituisce una lettura valida. Il modello può citare fonti consultate tramite strumenti, senza doverle sostituire con un riferimento arbitrario del blocco corrente.

Gli identificativi del catalogo e quelli di allineamento sono riconciliati tramite percorso e alias `file_id`/prefisso `page_id`; i collegamenti ai notebook usano le celle elencate. Un collegamento ambiguo non viene risolto scegliendo un file a caso. La qualità dell’associazione rimane visibile. La fonte PDF originale prevale sull’OCR; lo strumento visivo può mostrare una pagina o un frame originale al modello compatibile con immagini.

Le evidenze esterne richiedono URL effettivamente letti e confronto esplicito con notazione e ipotesi del corso. Le conoscenze generali rimangono dichiarate come tali. Le fonti originali non vengono riscritte.

## Esami e simulazioni

Solo domande estratte da PDF d’esame originali, con riscontro testuale negli intervalli letti, contribuiscono al profilo storico. Domande del docente, esercizi assegnati e problemi generati restano distinti. Scelta multipla richiede opzioni presenti nel testo. Il profilo espone numerosità, famiglie e limiti del campione; non stima probabilità di uscita.

Le prove esplicitamente riservate, copie esatte e soluzioni associate restano nascoste. Il confronto locale dei quesiti rimuove intestazioni e righe amministrative; nelle altre prove vengono filtrate le porzioni sovrapposte rilevate, lasciando accessibile il resto. Una soluzione senza corrispondenza affidabile ai sottopunti viene protetta più conservativamente. Nessuna procedura locale garantisce di riconoscere tutte le parafrasi.

La protezione si applica a testo, ricerca, contesto vicino, letture per righe e storico. Un PDF contenente porzioni protette non è scaricabile integralmente dal pannello; una pagina mista non è mostrata come immagine non filtrata. Rimane disponibile il testo consentito e le altre pagine. La simulazione esplicita sblocca quella prova soltanto nella sessione dedicata e ne registra l’esposizione.

## Revisioni e problemi

La prima fase di soluzione indipendente riceve attività senza risposta, soluzione, indizi, rubriche o risultati di verifica dell’autore. Le due revisioni successive devono dichiarare tutti i blocchi controllati e verificare le fonti. Numericamente si controllano i modelli dichiarati supportati: profondità di riduzione binaria, prefix sum, Amdahl e Gustafson. Questo non certifica automaticamente l’intero esercizio, né abilita esecuzione arbitraria di codice.

Dopo due revisioni il contenuto è indicato come revisionato, sempre con giudizio AI provvisorio. Correzioni automatiche dei capitoli sono limitate; un dubbio persistente sospende il blocco e le dipendenze dichiarate, conservando le parti utilizzabili. Il chiarimento dello studente viene salvato e riapre la revisione, non attribuisce da solo correttezza tecnica. Gli approfondimenti destinati al capitolo vengono messi in revisione prima di una nuova pubblicazione.

## Budget, continuità e interfaccia

Il budget iniziale delle fonti è il minore fra 32.000 token stimati e il 45% del contesto del modello, ridotto per lasciare spazio a istruzioni, strumenti e risposta. Il limite dell’output di preparazione è 8.192 token o il massimo inferiore del modello. Le fonti grandi proseguono da un checkpoint di caratteri, con contesto ai confini; nessun testo viene scartato fingendo copertura completa. Un compito che non entra nel contesto viene fermato con diagnostica esplicita.

Una richiesta di preparazione per volta, priorità alle chat fra compiti. Errori temporanei hanno tentativi limitati; risultati strutturalmente errati hanno una sola correzione. Un task completato è idempotente e non può essere sostituito da un risultato diverso. Riavvio, cambiamenti delle fonti o delle preferenze conservano lo storico e invalidano i risultati dipendenti.

L’interfaccia mostra fase, attività del provider, ultimo checkpoint, intervalli selezionati e revisioni. Le fonti sono raggruppate per lezione/data; le scelte sono correggibili. L’aggiornamento automatico non sposta focus o scroll. Tastiera, dark mode, formule accessibili, codice indentato, bozze e posizione restano disponibili.

## Verifica

Test Python coprono il percorso completo, protezioni, alias, ledger delle letture, intervalli grandi, revisione obbligatoria, problemi persistenti e ripresa. Test Pi usano il vero SDK con provider HTTP simulato e verificano anche che i temi protetti non entrino nei payload. Test browser usano un archivio sintetico separato.

`npm run verify:preparation` prepara localmente 30 quesiti e 20 decisioni sintetiche annotate. `-- --send --compare` chiama il provider selezionato confrontando richieste brevi e ampie; i risultati non creano progressi personali. Questo campione misura regressioni semantiche, non certifica il programma reale o le prestazioni dello studente.

La verifica didattica richiede ancora spiegazioni reali controllate, una sessione dello studente e una prova differita su problemi nuovi. Le prove tecniche e la revisione AI non sostituiscono queste evidenze.

### Chiarimenti sul perimetro e prove complete

La ricognizione può cercare e leggere slide, trascrizioni e notebook originali per ricostruire i confini, e anche i quesiti storici non riservati, attraverso lo stesso lettore con filtri delle altre fasi. Le soluzioni restano escluse. Prima di chiedere un confine allo studente, confronta programma, calendario e primi/secondi parziali pertinenti, con riferimenti verificabili. Una ricorrenza è evidenza di inclusione storica; un’assenza non dimostra esclusione dal programma attuale.

Due PDF «I part» e «II part» dello stesso appello sono due tracce di parti distinte: la data dell’appello non li rende due esami completi. Una prova completa unica rimane leggibile durante la preparazione del parziale: il profilo usa soltanto i quesiti/sottopunti pertinenti. Le parti inseparabili o dubbie vengono segnalate ed escluse dalle statistiche pertinenti, senza inventare un quesito autentico ridotto.

Nella scheda del perimetro, **Chiedi una verifica sulle fonti** conserva la bozza e permette una nuova ricognizione. Le indicazioni vengono salvate nell’obiettivo, conservando i risultati precedenti nello storico dei compiti e le riserve scelte. Il nuovo perimetro resta da confermare; questa azione non conferma o amplia silenziosamente l’esame. API: `POST /api/paths/:path/scope-followup` con `{note}`; disponibile solo nei nuovi percorsi non archiviati e non confermati.

### Verifica letterale dei quesiti e diagnostica

Il motore `selective-2.2` richiede un singolo quesito/sottopunto contiguo, con testo letterale e riferimenti alle pagine della prova, separando le citazioni delle evidenze teoriche da quelle della domanda autentica. Il controllo ignora spazi, righe vuote per le risposte e ligature tipografiche, mantenendo operatori matematici, esponenti e maiuscole significative nel codice. Usa soltanto gli estratti effettivamente letti delle pagine citate; le letture di righe vengono ricomposte soltanto se contigue, senza inventare continuità fra intervalli separati.

Tutti gli errori dei quesiti vengono restituiti insieme al modello nell’unico tentativo di correzione. Nessuna evidenza o domanda del lotto viene salvata prima che l’intera validazione riesca. Le risposte rifiutate vengono conservate nella tabella SQLite locale `prep_rejections`, con compito, errore e data; non entrano nel profilo d’esame o nei contenuti del tutor. Un riavvio mantiene checkpoint e quesiti validati, riprendendo soltanto il compito incompleto.

### Assegnazione automatica Luna/Sol

La modalità **Assegnazione automatica Luna/Sol**, in Modello e accesso, usa il provider OpenAI già configurato. La configurazione è reversibile e persistente; disattivandola si torna al modello singolo selezionato. Se viene selezionato un altro provider, la politica OpenAI non si applica. Vale dai prossimi compiti e non invalida le letture già completate.

| Lavoro | Modello iniziale |
|---|---|
| Selezione preliminare circoscritta, senza riletture tramite strumenti | GPT-6 Luna |
| Lettura tecnica, estrazione dei quesiti autentici e delle evidenze | GPT-6.1 Sol |
| Notebook/codice strutturato, trascrizioni incomplete, associazioni a bassa affidabilità | GPT-6.1 Sol |
| Perimetro, riconciliazione e mappa del corso | GPT-6.1 Sol |
| Spiegazioni, capitoli, esercizi, HTML e correzioni | GPT-6.1 Sol |
| Soluzione indipendente e revisioni disciplinare/didattica | GPT-6.1 Sol |
| Chat, valutazioni dello studente e ripassi | GPT-6.1 Sol |

Nella politica `hybrid-2`, la selezione riceve fino a 12 intervalli naturali, completi quando entrano nel budget e altrimenti marcati come troncati. Mantiene la motivazione completa del perimetro confermato; il profilo d’esame contiene conteggi e competenze, senza reinviare i testi dei quesiti. Usa un prompt specifico e nessuno strumento: la lettura tecnica successiva dispone ancora di tutti gli strumenti originali.

Sol verifica **solo le esclusioni** proposte da Luna, in una sessione indipendente con gli stessi originali e il perimetro, senza vedere il giudizio di Luna. Il servizio valida tutti gli ID e fonde le risposte senza modificare le decisioni restanti. Gli intervalli incerti restano selezionati e vengono letti da Sol nella fase disciplinare; non provocano una duplicazione immediata. Se un documento ha almeno otto intervalli già verificati e tutti esclusi, i successivi vanno direttamente a Sol per evitare un probabile doppio passaggio integrale. Questo cambia il modello, non esclude ulteriori fonti automaticamente.

Il candidato valido di Luna è salvato in SQLite **prima** della richiesta di verifica: un’interruzione o riavvio riprende la verifica residua, senza richiamare Luna. Il checkpoint è legato al compito, alle revisioni delle fonti, all’obiettivo e alla versione della politica. Un risultato strutturalmente non valido passa a Sol per la correzione completa; Sol dispone di un solo tentativo di riparazione. I consumi includono anche i tentativi precedenti alla ripresa.

La scelta non usa una percentuale di sicurezza dichiarata dal modello. Le regole sono euristiche, non dimostrano che ogni ambiguità verrà riconosciuta; mappa, contenuti e revisioni restano compiti esperti. Le fonti protette e i temi riservati rimangono esclusi anche durante il passaggio fra modelli.

L’avanzamento mostra il modello attivo e il motivo dell’assegnazione/passaggio. Ogni chiamata, incluse quelle fallite, è registrata nel database locale con output, modello, tempi e utilizzo restituito dal provider. I token di tutti i messaggi intermedi e dei due modelli vengono sommati; i token di ragionamento non vengono conteggiati una seconda volta. L’utilizzo dell’abbonamento non viene dedotto dai prezzi API.

Le richieste di preparazione restano sequenziali e la chat ha priorità fra i compiti. Un modello lettore non disponibile può essere sostituito dall’esperto. Un limite condiviso ChatGPT arresta invece il lavoro: non viene aggirato provando l’altro modello. Le configurazioni di budget vengono calcolate per il modello effettivamente usato. Le identità dei compiti includono modello e versione della politica; una ricognizione preliminare non crea compiti pendenti inutilizzati.

Configurazione: `preparation_routing` nelle impostazioni SQLite, politica `hybrid-2`. Endpoint `POST /api/model-routing` con `{enabled:boolean}`. `GET /api/models` riporta modello singolo e politica salvata; il salvataggio dell’impostazione non invia materiali al provider. Le chiamate effettive iniziano con la ripresa della preparazione o una richiesta di chat.

### Bibliografie e diagnostica della mappa

La bibliografia dei capitoli può superare 30 passaggi: contiene le fonti delle molte letture ricomposte nel capitolo. Il servizio valida ogni riferimento, conservando riserve, esclusione delle soluzioni e appartenenza al corso. La dimensione complessiva della mappa rimane limitata a 130.000 caratteri; singole attività e liste di evidenze mantengono i loro limiti più stretti. Non si eliminano fonti automaticamente per far passare una validazione.

Un errore di bibliografia indica `chapters[indice].sources`, l'identità del capitolo e il riferimento non valido. Richiesta iniziale e unica eventuale riparazione hanno una finestra separata di dieci minuti, entro venti minuti complessivi: una riparazione non viene interrotta dal timer della risposta precedente. I timeout espliciti arrestano il compito, lasciando i checkpoint disponibili.

### Pianificazione per contributi persistenti

I nuovi percorsi usano `compact-map-1`. La lettura sistematica delle fonti rimane completa; cambia il modo di ricomporne i risultati. Le richieste al pianificatore includono concetti, affermazioni, notazioni, ipotesi, esempi, problemi e riferimenti. Intervalli originali, copie degli estratti e impronte restano nel database e non vengono ricopiati in ogni richiesta. `read_preparation_evidence` recupera evidenze per ID, capitolo o pagina; gli strumenti per leggere gli originali rimangono disponibili nel tutor e nelle revisioni.

L’indice iniziale viene preparato una volta. Ogni lotto successivo produce soltanto contributi ai capitoli: ID delle evidenze, aggiunte didattiche, competenze e dubbi. Il servizio richiede che ogni evidenza proposta sia assegnata e rifiuta ID estranei, contributi incompleti o risultati obsoleti. Le bibliografie vengono unite dalle fonti effettive delle evidenze; non sono riscritte dal modello. Dopo tutti i contributi avvengono una riconciliazione complessiva e la revisione della mappa. Problemi bloccanti richiedono una nuova riconciliazione, riusando i contributi compatibili anziché rileggerli.

I contributi sono persistenti e idempotenti. L’impronta della costruzione comprende strategia, obiettivo, contenuto delle evidenze e revisioni delle fonti. Se cambiano questi dati, il risultato precedente non viene applicato al nuovo compito. La migrazione esplicita `preparation_optimize_map` mantiene i risultati del percorso attivo: le evidenze già incorporate da lotti completati sono riconosciute solo se contenuto e provenienza coincidono. I percorsi archiviati rimangono esclusi.

La revisione della mappa e la produzione dei capitoli ricevono un contesto pertinente e gli strumenti di recupero, anziché tutte le copie dei testi originali contenute nelle evidenze. La scelta del modello conserva Sol per pianificazione, contributi e verifiche. La ricognizione preliminare del prossimo compito viene riutilizzata per l’avvio solo se il database non è cambiato: nessuna seconda scansione identica per scegliere il modello.

L’interfaccia distingue evidenze organizzate, contributi salvati e contenuti revisionati. Questi contatori non misurano la comprensione dello studente.


La riconciliazione usa una sessione dedicata senza strumenti: compone il progetto dai contributi; la revisione successiva verifica gli originali. La risposta nuova è limitata a 24000 caratteri. Bibliografie e copertura sono ricostruite dal servizio. Il contenuto didattico mantiene il limite di 130000 caratteri; per questa composizione il totale con riferimenti validati ha un limite separato di 260000.

Se una precedente riconciliazione dello stesso percorso e della stessa impronta è interrotta, il recupero decodifica soltanto campi JSON completi. Quando chapters e gaps sono integri, vengono conservati esattamente; una nuova richiesta completa soltanto i metadati mancanti. Stringhe e oggetti troncati non vengono riparati né interpretati come fatti. La composizione passa gli stessi controlli di fonti, perimetro, prerequisiti e copertura e resta soggetta alla revisione della mappa. Le lacune e le esclusioni precedenti sono conservate; le chiamate originali rimangono nello storico.


Le correzioni successive a una revisione usano un delta sul piano corrente, anziché rigenerare l'intera mappa. La risposta troncata non è riapplicata dopo un completamento riuscito. I delta aggiungono riferimenti originali effettivamente letti dal revisore, rettificano il progetto del capitolo e possono revocare esclusioni o archiviare singole lacune con una motivazione. Le lacune archiviate e le esclusioni revocate restano nello storico, distinguibili dai vincoli attivi. Le rettifiche della selezione riguardano soltanto pagine originali fornite nel compito e conservano lo stato precedente in `prep_scope_changes`; non estendono automaticamente l'inclusione al documento intero. Fonti, corso, identità, prerequisiti, perimetro e copertura sono nuovamente validati dal servizio prima della scrittura. Una nuova revisione completa controlla il risultato; la correzione non può approvarsi da sola. I limiti ai cicli vengono conteggiati per versione del protocollo di correzione, mantenendo tutti i rapporti precedenti.


Il limite strutturale dei capitoli è esplicito in `chapter_limits`: al massimo 48 blocchi e 180000 caratteri. Spiegazioni ed esercizi brevi possono superare i precedenti 24 blocchi senza rendere invalido il capitolo. I messaggi di errore distinguono numero di blocchi, tipo del campo e dimensione effettiva; il modello riceve gli stessi limiti applicati dal servizio. Non si riduce il controllo di citazioni, soluzioni, provenienza o revisioni. Un risultato precedentemente rifiutato per il solo numero di blocchi può essere recuperato integralmente dal registro della chiamata, dopo rivalidazione ordinaria: non richiede una nuova generazione e non è pubblicato prima delle revisioni.

### Ripresa di una revisione con citazioni incomplete

Il validatore elenca gli ID mancanti in `checked_sources` e le citazioni prive di una lettura registrata. Le fonti originali incluse nell’input e quelle recuperate con strumenti appartengono allo stesso inventario cumulativo; riceverle non equivale a dichiararle automaticamente verificate.

Se un controllo sulle fonti interrompe la revisione, la ripresa può riutilizzare un risultato rifiutato dello stesso compito immutato e le relative ricevute di lettura. La riparazione riceve il risultato precedente, i controlli mancanti e i blocchi da ricontrollare, con una sola richiesta di riparazione prima di fermarsi di nuovo in caso di errore. Nessuna fonte viene aggiunta automaticamente fra quelle verificate e tutti i controlli restano obbligatori prima della pubblicazione.

Nelle revisioni, `checked_sources` e i riferimenti dei rilievi possono contenere sia passage ID sia URL HTTPS. I primi richiedono ricevute in `prep_reads`, gli URL una lettura `read_web_page` registrata in `prep_external` per lo stesso compito: una lettura dell'autore o di un altro revisore non basta. La copertura richiesta comprende anche `external_sources` dei blocchi. Il recupero rivalida integralmente le revisioni rifiutate, incluse quelle fermate dal precedente errore di classificazione degli URL, e conserva tutti i rilievi; un risultato ora valido viene salvato senza richiederlo nuovamente al modello.

La risoluzione indipendente richiede esattamente una risposta con ragionamento per ogni blocco `activity`. Un contributo riferito a un blocco `text` esistente viene conservato in `supplementary_solutions`, senza sostituire esercizi mancanti o invalidare soluzioni complete. ID inesistenti, duplicati e risposte incomplete restano rifiutati, con indicazione degli ID mancanti. Anche questa fase può recuperare un output rifiutato dello stesso task dopo rivalidazione; l'output originale rimane nella diagnostica e nel risultato del task, senza nuove richieste al modello quando già completo.

### Correzione del capitolo senza rigenerazione integrale

`repair_chapter` corregge separatamente i blocchi citati nei rilievi disciplinari e didattici, inclusi i warning. Ogni richiesta restituisce un solo blocco completo con identità e tipo invariati; i blocchi senza rilievi restano identici. Il contesto contiene i blocchi vicini e le dipendenze, l'indice e le fonti pertinenti, senza ripetere tutto il capitolo o il profilo degli esami. Le richieste successive ricevono le sostituzioni già completate come contesto, anche dopo una ripresa, evitando di reintrodurre contenuti superati dalle correzioni. Rilievi globali senza un blocco identificabile richiedono una verifica a blocchi dell'intero capitolo.

Ogni sostituzione completa viene salvata nelle metriche del compito immutato. Dopo una pausa o un errore del provider si riparte dal blocco mancante. Un risultato parziale non diventa mai una bozza pubblicabile: il capitolo ricomposto passa gli stessi controlli di fonti, struttura e modelli deterministici, poi nuove revisioni indipendenti. Una bocciatura del capitolo ricomposto conserva le sostituzioni. Alla ripresa, il server rivalida ogni blocco rispetto allo stesso task, alle fonti lette e ai controlli deterministici: i blocchi validi restano completati, gli altri sono soltanto input non fidato da ricontrollare. Le fonti originali complete del blocco e dei relativi rilievi vengono fornite automaticamente alla richiesta di correzione, con ricevute di input; le nuove citazioni richiedono comunque lettura tramite strumenti. I blocchi invariati mantengono la validazione della bozza precedente, mentre tutte le modifiche richiedono le proprie ricevute e il capitolo ricomposto passa ancora i controlli finali. La UI mostra quanti blocchi corretti sono stati salvati.

### Scrittura del capitolo con checkpoint intermedi

Anche la creazione iniziale usa ora richieste limitate: un indice dei blocchi con ruoli didattici e copertura degli indici di `exam_skills`, poi al massimo due blocchi per risposta. L'indice include spiegazione, esempio svolto e prova autonoma; ciascuna risposta è limitata a 16000 caratteri. Lo stesso contesto e le letture rimangono nella sessione tra richieste; una ripresa apre una sessione con il task immutato, l'indice e i blocchi già salvati. Il limite temporale si applica alla singola richiesta. I blocchi ricevuti e validati sono salvati prima di procedere e non possono essere riscritti o rimossi da un successivo checkpoint.

Il servizio può recuperare un prefisso di oggetti JSON completamente decodificati dai vecchi output interrotti. Non chiude stringhe o oggetti troncati. Il recupero riguarda soltanto lo stesso task e viene validato nuovamente su struttura, fonti lette, dipendenze e verifiche deterministiche; al primo avvio viene conservato anche prima di pianificare la parte mancante. Per le risposte del nuovo protocollo si recuperano soltanto prefissi validi di una richiesta interrotta, con gli ID attesi dal checkpoint. Un risultato completo rifiutato dal validatore non viene promosso automaticamente.

Gli URL già verificati tramite `read_web_page` vengono separati in `external_sources`, preservando testo e link; `sources` rimane riservato ai passage ID del corso. Le verifiche di scaling riconoscono alias non ambigui: `p` per `processors`, `parallel_fraction` per la quota di Amdahl e `serial_fraction` per quella di Gustafson. I valori originali restano conservati; campi discordanti e risultati errati sono rifiutati. Mancanze dei parametri producono un errore leggibile, non un `KeyError`.

I checkpoint intermedi non sono capitoli pubblicati. Il capitolo ricomposto passa ancora il commit ordinario, la risoluzione indipendente, la revisione disciplinare e quella didattica prima di essere reso disponibile. La schermata di preparazione mostra quanti blocchi sono salvati o recuperati. Il budget di strumenti è per singolo messaggio, così una sessione con più batch non esaurisce per sempre la possibilità di leggere fonti.

Verifica del recupero sul caso reale: 26 blocchi completi recuperati, con testo, domande, soluzioni e risposte invariati; indice da 28 blocchi; generati soltanto i due mancanti e completato il commit della bozza. La preparazione è passata a `review_solve`. Verifiche locali: 75 test applicativi, 53 test backend e build passati; il flusso a blocchi è coperto anche da un test SDK con risposte simulate.
