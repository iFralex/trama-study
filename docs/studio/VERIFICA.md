# Verifica della prima versione — 16 ottobre 2026

## Esiti tecnici

- Build TypeScript/Vite completata.
- Suite originale: 113 test raccolti, esito OK, 52 skip condizionati alle dipendenze disponibili nell'ambiente principale. Eseguita con TMPDIR canonico su macOS.
- Ambiente nativo: 25 test OCR, allineamento e tutor, tutti passati. Include i controlli che richiedono il runtime visivo separato.
- TypeScript/SDK: 6 test passati. Pi viene realmente incorporato: provider HTTP locale simulato, streaming, chiamate agli strumenti, creazione attività, contesto delle interazioni, valutatore separato e conservazione del messaggio quando il provider restituisce un errore.
- Browser: 3 percorsi passati. Domanda errata → indizio → risposta corretta → previsione → simulatore → ricarica immediata → ripresa → completamento → domanda autentica → variante → richiamo → fonte PDF visibile. Verificati anche simulazione senza aiuti, mancato accesso al modello, tastiera, focus e bozza successiva durante una risposta.
- Lanciatore verificato usando configurazione e disco dati reali, senza aprire un browser durante il controllo.

## Corpus reale

Indicizzati 3.536 passaggi di Parallel Computing 2025-26. Otto domande annotate in italiano/inglese recuperano almeno un documento atteso nei primi dieci risultati (8/8). Il risultato misura questi casi di ricerca, non l'accuratezza globale del tutor. Il rapporto dettagliato è nella cartella dati: `.state/studio/retrieval-verification.json`.

La verifica conserva qualità e provenienza di trascrizioni e allineamenti. Le discrepanze tra data nel nome e nell'intestazione dei temi sono segnalate senza modificare gli originali.

## Accesso al modello e validazione didattica

Al momento della verifica non risultano modelli autenticati disponibili attraverso Pi. L'interfaccia offre **Modello e accesso** per collegare il provider. L'integrazione SDK è testata con un provider locale simulato; non è stato valutato il comportamento di un modello commerciale sui materiali personali senza un accesso configurato.

Il percorso curato PRAM/riduzione/scan ha risultati deterministici verificati. Spiegazioni e correzioni aperte del modello rimangono provvisorie. Una sessione reale dello studente e una verifica differita su problemi nuovi sono ancora necessarie per valutare l'efficacia didattica. I test temporali verificano la regola delle 24 ore, non l'apprendimento umano.

I tentativi automatici nel browser usano un archivio fittizio separato. Non vengono registrati come risultati personali nel corso reale. Materiali, video, trascrizioni originali e accessi WeBeep non vengono modificati.


## Estensione ricerca e memoria — 16 ottobre 2026

- 13 test Python del tutor passati, inclusi navigazione file/righe, lettura di codice e HTML, recupero dello storico, ripresa della sessione selezionata, indice incrementale, vettori obsoleti e filtri d'esame.
- 7 test TypeScript/Pi passati; verificati anche strumenti di memoria/ricerca e blocco degli indirizzi web locali.
- 4 percorsi Playwright passati, incluso accesso allo storico dall'apertura, ripresa e pulsante ChatGPT, oltre ai percorsi precedenti.
- Modello ONNX multilingue scaricato e usato realmente, 3.538 passaggi indicizzati; nessun passaggio pendente al riavvio.
- Ricerca ibrida: 11/11 casi annotati con documento atteso nei primi dieci risultati, inclusi 3 casi di parafrasi; rapporto `.state/studio/hybrid-verification.json`. È una verifica limitata di recupero, non dell'accuratezza del tutor.
- Ricerca web pubblica provata dal vivo; PDF universitario di Washington estratto con URL, pagine e momento di consultazione. Le verifiche TLS restano attive: una fonte con certificato non valido restituisce un errore.
- L'accesso OAuth personale e il comportamento di un modello commerciale richiedono ancora il login dell'utente. Le regole su conoscenza generale, confronto delle formule e chiarimenti sono istruzioni esplicite, non un rilevatore infallibile di errori.


## Percorso dalle basi — 16 ottobre 2026

- 22 test Python del tutor e del percorso passati: piano ancorato alla lezione, assenza di quiz iniziale, ordine dei materiali, OCR candidato, cursori per lezione/argomento, richiamo con ritorno al punto precedente e persistenza.
- 9 test TypeScript/Pi passati. Il nuovo test usa il vero bridge Python e SDK Pi con provider simulato per leggere lezione e fonte, salvare il piano e creare una spiegazione per principianti.
- 5 percorsi Playwright passati, compreso avvio dalle basi, provider assente, richiesta conservata, ricaricamento, ripresa e programma delle lezioni.
- Catalogo reale verificato in memoria: 14 lezioni in ordine, dal 16 settembre al 4 novembre 2025; 12 con trascrizione indicizzata e 2 con soli OCR/associazioni, segnalate. Prima lezione: 26 passaggi e 7 pagine PDF associate. Nessuna sessione fittizia aggiunta al catalogo personale.
- I contenuti del tutor commerciale richiedono una verifica didattica reale: questi test verificano contratto, fonti, salvataggi e UX, non certificano correttezza o apprendimento.


## Formule accessibili — 16 ottobre 2026

12 test TypeScript/Pi e 6 percorsi browser passati. Descrizioni italiane reali verificate per `T(n)=an+b`, frazioni, quadrati e pedici, senza ripetizione dell'annotazione TeX. La formula è un singolo oggetto accessibile e il hit test sulla `n` restituisce il contenitore intero. Verificate persistenza, modalità testuale e ripristino del MathML. Il test non avvia la voce nativa macOS; resta necessaria la prova con la lettura sotto il puntatore dell'utente.


La prova dell’utente su macOS ha mostrato che il ruolo matematico con sola etichetta non veniva letto sotto il puntatore. La modalità Formula intera ora usa un vero nodo di testo, sovrapposto con dimensioni corrispondenti alla formula; il disegno resta visibile e non viene duplicato nell’albero accessibile. Il test browser verifica StaticText, rettangolo e hit test. L’utente ha confermato che la nuova versione viene letta sotto il puntatore sul proprio Mac.


Lettura naturale: 13 test TypeScript/Pi e 6 percorsi browser passati; build completata. `T(n)=an+b` produce «T di n uguale a a per n più b». Verificati anche funzione con argomento composto, prodotto implicito con parentesi, frazioni, potenze e pedici. La nuova formulazione vocale è verificata nel testo accessibile; la pronuncia effettiva dipende dalla voce macOS.


Posizione del campo messaggi: build e 7 percorsi browser passati. Una chat breve occupa almeno l’altezza disponibile e mantiene il campo in basso; con messaggi lunghi il campo resta raggiungibile durante lo scorrimento. Verificati bozza e focus conservati durante la crescita del contenuto e campo accessibile anche su schermo stretto.


Confronti inline: il caso reale `i ≤ n` era codice inline in una tabella Markdown, fuori dal rendering matematico. Ora i brevi confronti isolati in codice inline espongono la descrizione completa, mantenendo il testo visibile; blocchi di codice e programmi restano esclusi. Verificati ≤, ≥, ≠ e forme ASCII, con 15 test TypeScript/Pi, 7 percorsi browser e build passati.


Pseudocodice nelle domande: verificato l’esempio RAM originale, con righe e rientri conservati anche quando manca il blocco Markdown. Il renderer ripristina gli spazi rimossi dalla conversione Markdown e i paragrafi delle attività li visualizzano. I blocchi di codice mantengono la resa standard. Il tutor e lo schema dello strumento richiedono blocchi Markdown per codice/pseudocodice futuri. Build, 15 test TypeScript/Pi e 8 percorsi browser passati, incluso confronto delle coordinate effettive delle righe e dei rientri. Nessuna modifica ai contenuti o tentativi personali.


## Corso personale — 17 ottobre 2026

- 44 test Python dello studio passati: perimetro confermato, lettura riprendibile, checkpoint idempotenti, copertura, esclusione dei temi riservati, profilo entro perimetro, fonti cambiate, versioni, bozze compatibili, sessioni multiple, diario ed evidenze, preferenze e richiami. Gli indicatori distinguono aiuti/autonomia/conferma differita e mantengono il qualificatore provvisorio; il criterio temporale è verificato con date simulate.
- 16 test TypeScript/Pi passati. Il nuovo percorso usa davvero SDK Pi e bridge Python con provider HTTP simulato: scheda dell’esame, errore nel secondo blocco, ripresa senza rianalizzare il primo, ricerca, piano, capitolo, nuovo richiamo, valutatore isolato e scheda FSRS. I payload del provider non contengono i testi dei temi o delle soluzioni riservati.
- 12 percorsi Playwright passati su un archivio sintetico separato: capitolo/chat affiancati, mobile, fonti/PDF, tastiera, focus e bozze, ripresa, diario correggibile, provider assente, oltre alle funzioni precedenti. Verificata anche la bozza della domanda successiva mentre è ancora in coda il salvataggio di un’attività.
- Build TypeScript/Vite completata. Interfaccia desktop ispezionata tramite screenshot locale.
- Inventario reale verificato localmente su copia temporanea di SQLite: 91 documenti, 32 candidati d’esame, 12 documenti di trascrizione, 14 allineamenti, 1 duplicato e 5 avvisi sui documenti. Nessun tentativo sintetico aggiunto all’archivio personale.
- Verifica reale del 17 ottobre 2026 con OpenAI `gpt-6.1-sol`: **3/3 quesiti annotati classificati correttamente** per formato, competenze e appartenenza al perimetro dichiarato. PRAM: domanda aperta inclusa; SIMD: pseudocodice incluso; Pack: formato misto escluso dal primo parziale. Segnalate anche le discrepanze tra date nei nomi dei file e intestazioni. L’invio, inizialmente respinto dalla revisione automatica, è stato eseguito dopo autorizzazione esplicita dello studente per questi tre estratti e questa destinazione. Nessuna sessione o progresso personale creato. Rapporto locale: `/private/tmp/studio-curriculum-real-eval.json`. Il campione verifica classificazione e perimetro, non soluzioni, spiegazioni o correttezza di un intero corso. Il comando senza `--send` continua a preparare soltanto il payload locale.
- Restano da verificare la correttezza didattica del primo capitolo reale con il provider personale, una sessione dello studente e una prova differita su problemi nuovi. I test tecnici non dimostrano apprendimento o un voto atteso.


## Temi riservati pertinenti — 17 ottobre 2026

Rimossa la preselezione alfabetica di due temi nell’inventario, che non conosceva ancora l’obiettivo. I suggerimenti arrivano nella scheda del perimetro, con motivazione e distinzione tra parziali ed esame completo; se la pertinenza non è determinabile, il modello deve omettere il tema. Il server rifiuta raccomandazioni di temi già esposti, duplicati, illeggibili, non d’esame o con etichetta esplicita incompatibile. Un perimetro ancora ambiguo non ammette suggerimenti. Le etichette sconosciute richiedono valutazione del modello, non sono una verifica deterministica del contenuto.

Verificati 39 test Python (studio e corso personale), 16 test TypeScript/Pi, build e il percorso browser mirato alla creazione dell’obiettivo: nessuna preselezione né tema riservato prima della scheda. Le prove usano dati sintetici e nessuna nuova chiamata al provider personale.


## Ripresa dopo citazioni rifiutate — 17 ottobre 2026

Una preparazione reale si è fermata durante la lettura di un allineamento: il JSON del modello citava passaggi fuori dall’insieme consentito per la scheda cumulativa. Il checkpoint rifiutato non è stato salvato; quelli precedenti sono conservati. Ogni compito di lettura ora espone `allowed_sources` e le istruzioni distinguono i riferimenti ammessi dagli ID presenti dentro metadati/allineamenti. Un errore di appartenenza delle citazioni permette una sola richiesta di correzione nella stessa sessione, senza aggirare il validatore. Se la correzione resta invalida, la preparazione si ferma e conserva i checkpoint.

40 test Python, 17 test TypeScript/Pi e build passati, compresa la ripresa con citazioni corrette e il rifiuto persistente dopo il limite di una correzione. I test del recupero usano un provider simulato.


## Schede cumulative e budget — 17 ottobre 2026

La preparazione reale si è successivamente fermata a 124 blocchi sul controllo generico di scheda mancante/troppo lunga; la scheda cumulativa precedente era di 15.652 caratteri, prossima al limite. Il risultato rifiutato non era stato conservato, quindi non si può distinguere retroattivamente sintesi assente da sforamento. Ora il validatore distingue i due casi e riporta dimensione e limite. Il compito espone budget obiettivo 8.000 e massimo 16.000 caratteri per l’intero JSON, con istruzioni di raggruppare concetti e non accodare cataloghi di frame. Anche queste due condizioni ammettono una sola correzione, senza tagliare automaticamente contenuti o allentare il controllo.

Passati 41 test Python, 17 test TypeScript/Pi, controllo TypeScript e build; il test del motore copre sia la correzione riuscita sia il rifiuto persistente per lunghezza, sintesi e citazioni.


## Motore selettivo 2 — 17 ottobre 2026

Implementazione completa delle fasi: perimetro, analisi dei temi originali, selezione per intervalli, evidenze incrementali, mappa e revisione, capitoli, soluzione indipendente, revisione disciplinare e didattica, correzione/pubblicazione. Le analisi del motore precedente rimangono archiviate e non vengono importate nel nuovo percorso; anche progressi e strumenti di evidenza sono circoscritti alla nuova identità del percorso.

- 67 test Python dello studio passati, con protezioni su pagine miste, contesto vicino, letture/grep, alias di PDF/notebook, intervalli grandi riprendibili, provenienza dei quesiti, verifica numerica, revisioni complete, chiarimenti e riserve tra obiettivi.
- 19 test TypeScript/Pi passati. Il nuovo percorso usa l’SDK reale con un provider HTTP simulato, attraversa tutte le fasi, supera un errore temporaneo e non invia i testi delle prove riservate. Le risposte indipendenti non ricevono chiavi né risultati delle verifiche dell’autore.
- 14 percorsi browser su archivio sintetico separato: regressioni precedenti più fasi/selezione, archivio, chiarimenti, assenza di focus sottratto e bozze. Il controllo visivo ha rilevato un errore transitorio prima del caricamento del corso: corretto con un controllo iniziale e cancellazione dell’errore al cambio corso; aggiunta regressione browser.
- Build TypeScript/Vite completata. Nessuna modifica a credenziali, originali o ambienti di download/trascrizione/allineamento.
- Verifica su copia temporanea dell’archivio reale: nuovo piano assente, zero evidenze ereditate, due temi esplicitamente scelti protetti. Riconciliati 1.582 collegamenti; l’alias legacy del PDF introduttivo ora risolve il documento corretto. La precedente associazione dell’intero notebook è sostituita dalle sole celle indicate.
- Benchmark semantico con OpenAI gpt-6.1-sol su 30 quesiti e 20 decisioni **sintetiche annotate**: revisione 2 del campione, 50/50 con due richieste brevi (24.018 ms) e 50/50 con una ampia (18.627 ms). Rapporto locale `/private/tmp/preparation-semantic-report-v2-20261017.json`; nessun progresso personale creato. Non è una prova di accuratezza sull’intero corpus reale, né un benchmark del contesto massimo.
- Il primo rapporto, conservato in `/private/tmp/preparation-semantic-report-20261017.json`, aveva 48/50 e 49/50: l’ispezione ha trovato una classificazione gold errata del formato di una domanda aperta con origine incerta e un perimetro sintetico ambiguo sulle metriche. Corrette le annotazioni/perimetro, senza alterare il rapporto iniziale.

Rimangono verifiche umane e temporali: correttezza didattica dei capitoli reali prodotti, sessione dello studente e prova differita su problemi nuovi. La doppia revisione AI non equivale a un giudizio indipendente garantito. Le sovrapposizioni non identificabili e le associazioni candidate restano limiti espliciti.


Attivazione locale: commit `0ca6924`, servizio aggiornato sulla porta 4326, backup SQLite consistente prima della migrazione. Verificati integrità SQLite, conteggi storici conservati e modello configurato invariato. Il vecchio percorso è archiviato; il nuovo ha zero evidenze/piani ereditati. La prima ricognizione reale con il provider configurato è terminata senza errore e chiede conferma del confine del primo parziale (inclusione di Memory consistency & synchronization e OpenMP part 1 secondo il calendario). La lettura approfondita resta in attesa di questa risposta; nessun confine è assunto silenziosamente.

### Verifica del perimetro con gli esami storici — 17 ottobre 2026

Motore `selective-2.1`: ricognizione su quesiti storici e materiali disciplinari originali non riservati; chiarimenti dello studente persistenti e nuova ricognizione prima della conferma. I PDF di prima/seconda parte degli appelli ordinari non vengono equiparati automaticamente a prove complete. Le prove complete rimangono analizzabili per quesito anche per un obiettivo parziale. Vengono riaperte le sole esclusioni automatiche obsolete, conservando quelle manuali.

Verifiche: 71 test Python, 19 test TypeScript/Pi e i 3 flussi Playwright della preparazione superati; typecheck/build riusciti. Test aggiunti per protezione delle riserve/soluzioni nella ricognizione, lettura delle slide, riapertura del perimetro senza conferma, prova completa non esclusa, filtraggio del profilo per quesito, bozza accessibile persistente e provider non disponibile. Il primo test browser ha individuato l’etichetta implicita di una textarea che inglobava il testo della bozza: corretta con etichetta esplicita separata e verificata dopo ricaricamento.

Prima dell’attivazione è stato eseguito un backup SQLite locale. Nella ricognizione reale i precedenti non riservati confermano la presenza storica della memory consistency e di OpenMP nella prima parte. Queste evidenze non dimostrano da sole il confine dettagliato dei costrutti OpenMP del programma corrente: viene completato il confronto con calendario, slide e notebook. Le prove riservate restano protette e il perimetro aggiornato richiede conferma.

Esito della ricognizione reale: completata senza errori, stato `confirm`, nessun chiarimento residuo obbligatorio. Le trascrizioni del 28 ottobre (circa 30 minuti) e del 30 ottobre (circa 88 minuti) contengono la delimitazione esplicita del docente: il blocco successivo alla memory consistency appartiene alla seconda parte e non al prossimo midterm. Il confronto con le slide e il notebook evita quindi di includere automaticamente OpenMP/Pthreads sulla sola base del calendario preliminare o dei precedenti appelli. I passaggi chiave sono stati ricontrollati nel loro contesto. Il perimetro rimane una proposta documentata da confermare; nessuna pagina riservata letta nel compito.

### Diagnosi del blocco nell’estrazione dei quesiti — 17 ottobre 2026

Il primo tentativo sul tema dell’8 novembre 2022 è stato rifiutato perché una domanda citava fonti esterne alla prova. La correzione è stata rifiutata per testo non attestato. Le vecchie risposte rifiutate non erano conservate: non è possibile identificare retrospettivamente la domanda o attribuire con certezza quel secondo errore a una parafrasi o a un difetto di impaginazione.

L’ispezione ha individuato altri difetti riproducibili: confronto sull’insieme indiscriminato degli estratti letti anziché sulle pagine citate; righe per le risposte conservate come parole; rimozione di operatori matematici e distinzione fra maiuscole/minuscole; arresto al primo errore, che poteva consumare la riparazione senza far emergere gli altri quesiti invalidi. Questi difetti sono stati corretti senza introdurre corrispondenze semantiche permissive. La diagnostica conserva ora anche la risposta rifiutata.

Verifiche: 75 test Python e 19 test TypeScript/Pi superati, typecheck/build riusciti. Il test con SDK Pi e provider simulato inserisce una domanda inventata, ne verifica rifiuto e salvataggio diagnostico e restituisce una correzione valida prima di completare il percorso; resta inclusa la simulazione di errore transitorio 503. Nuovi casi controllano segni, esponenti, identificatori del codice, ligature, fonti estranee e atomicità di un lotto con più domande errate.

Nuova esecuzione reale del primo tema: checkpoint riuscito senza riparazione, 13 quesiti originali salvati, 11 pertinenti e 2 fuori perimetro. I testi di questo nuovo risultato superano anche il vecchio confronto: il successo dimostra il funzionamento del protocollo corretto, ma non permette di ricostruire il testo del precedente tentativo perso. Backup locale eseguito prima dell’attivazione; analisi ripresa dal checkpoint, mantenendo protetti i temi riservati.

### Assegnazione del lavoro a Luna e Sol

Motore `selective-2.3`, politica `hybrid-1`: Luna per letture/estrazioni strutturate; Sol per decisioni, ambiguità, codice strutturato, produzione e tutte le revisioni. Configurazione reversibile nell’interfaccia; modello e motivo del passaggio visibili nel pannello di preparazione. La modalità singola e gli altri provider mantengono il comportamento precedente.

Verifiche: 77 test Python, 25 test TypeScript/Pi, build/typecheck e cinque flussi browser della preparazione superati. Il test di integrazione usa due modelli simulati attraverso il vero SDK Pi: una citazione inventata, un’esclusione e una notazione dubbia passano dal lettore all’esperto senza pubblicare il risultato intermedio; il capitolo viene pubblicato solo dopo le due revisioni complete. Verificati anche 503 temporaneo, quota condivisa senza tentativi sull’altro modello, chat/valutazioni/ripassi esperti, idempotenza del registro delle chiamate e persistenza al riavvio. Il cambio del modello visualizzato non sottrae focus né perde la bozza. L’interruttore delle impostazioni mostra il salvataggio asincrono e conserva la scelta precedente se la richiesta fallisce.

Backup SQLite locale creato prima dell’attivazione del codice. I 184 quesiti reali e i checkpoint rimangono conservati. La ripresa reale con Luna è temporaneamente sospesa: la revisione automatica ha richiesto una conferma esplicita dell’invio delle fonti non riservate a Luna, oltre alla richiesta di assegnazione dei compiti. Nessun payload del corso è stato inviato dai due comandi bloccati. I test di questo incremento usano provider simulati e fixture separate.

Attivazione successiva: ricevuta conferma esplicita «Sì, autorizzo l’invio a Luna e la ripresa» per trascrizioni, slide e materiali non riservati. La politica `hybrid-1` è stata salvata come attiva e la preparazione è stata ripresa dal checkpoint. Restano conservati i 184 quesiti; nessuna rielaborazione dei temi già completati è necessaria.


### Selezione circoscritta e confronto dei costi (17 ottobre 2026)

Politica `hybrid-2`: Luna solo per selezione, Sol per letture tecniche e revisioni. Confronto reale e limiti in [CONFRONTO_MODELLI.md](CONFRONTO_MODELLI.md). Verificati 78 test Python dello studio, 32 test TypeScript/Pi e cinque test Playwright della preparazione; typecheck e build completati. I test aggiunti controllano ID mancanti/duplicati/estranei, fusione limitata alle esclusioni, conservazione delle fonti incerte e recupero della verifica esperta senza richiamare Luna. Le prove HTTP/Pi sintetiche verificano anche riserve, errori del provider e arresto sui limiti condivisi. Nessuna chiamata reale al provider nei test automatici di regressione; i confronti reali sono separati e i loro rapporti rimangono nella cartella dati.
