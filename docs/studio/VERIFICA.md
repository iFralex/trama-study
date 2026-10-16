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
- Preparato il payload locale di tre quesiti reali annotati (definizioni PRAM, pseudocodice SIMD, Pack del secondo parziale). La classificazione con OpenAI gpt-6.1-sol non è stata eseguita: la revisione automatica ha respinto l’invio degli estratti perché richiede autorizzazione specifica per quel payload e quella destinazione. Il comando di verifica senza --send prepara solo il file locale.
- Restano da verificare la correttezza didattica del primo capitolo reale con il provider personale, una sessione dello studente e una prova differita su problemi nuovi. I test tecnici non dimostrano apprendimento o un voto atteso.
