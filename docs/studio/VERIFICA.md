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
