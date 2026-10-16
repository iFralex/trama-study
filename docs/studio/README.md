# Studio: tutor locale con Pi

Apri `Studio.command`, oppure `Avvia.command` → operazione 5. Il browser si apre su `http://127.0.0.1:4326`. Lascia aperto il terminale; Ctrl+C ferma il servizio. Il primo avvio prepara e compila l'interfaccia. Node.js 22+ e il runtime visivo Python sono necessari. Dipendenze, cache, conversazioni e database seguono la cartella dati configurata.

Scegli il corso e premi **Riprendi il percorso**. Una sessione precedente conserva attività, versione, bozze, interazioni e tentativi. **Nuova sessione** conserva lo storico. Obiettivo e tempo si modificano nella sessione. **Modello e accesso** elenca i modelli autenticati e offre i flussi API/OAuth dei provider Pi. Il programma non presuppone che un abbonamento dia accesso a ogni modello. Le fonti recuperate e le risposte necessarie vengono inviate al provider scelto; i file originali restano sul disco.

## Prima versione

- Chat Markdown/LaTeX con attività incorporate e pannello espandibile.
- Importazione incrementale, basata su SHA-256, di PDF, notebook, trascrizioni e allineamenti. Nessuna esecuzione dei notebook.
- Ricerca FTS5 con traduzioni mirate italiano/inglese e contesto vicino al passaggio.
- Fonti originali: pagina PDF renderizzata localmente (anche senza plugin PDF), PDF completo, video al timestamp, testo delle celle e qualità delle associazioni.
- Percorso curato PRAM → riduzione → prefix sum → domanda autentica → variante → richiamo. Per altri argomenti e corsi l'agente cerca le loro fonti e crea attività; non viene riutilizzato automaticamente il percorso PRAM.
- HTML/CSS/JavaScript isolato, con eventi osservabili. Una manipolazione salva lo stato senza chiamare il modello a ogni cambiamento. Le azioni del laboratorio attendono la conferma del salvataggio prima di mostrare l’avanzamento.
- Risposte numeriche/scelte/completamenti curati verificati automaticamente; giudizi su risposte aperte e attività generate sempre provvisori.
- Aiuti registrati, contestazione delle correzioni, richiami FSRS. Una conferma a distanza richiede due problemi diversi risolti senza aiuti e separati da almeno 24 ore.
- Un tema intero riservato, con soluzioni escluse da ricerca e contesto durante la prova. La chat è sospesa nella simulazione; il valutatore isolato interviene alla consegna.

Le domande autentiche vengono estratte dai file disponibili. Le rubriche proposte e le spiegazioni curate sono distinte dalle soluzioni ufficiali. La data nel nome del file e quella nell'intestazione restano entrambe disponibili se discordanti.

## Persistenza

`<cartella dati>/.state/studio/studio.sqlite3` è scritto da un solo processo Python. Il registro append-only degli eventi contiene identità, versione, azione, payload e momento; gli ID duplicati non creano tentativi duplicati. Le attività vengono versionate. Le bozze hanno anche una copia locale nel browser; gli eventi non ancora confermati dal disco vengono ritentati alla riapertura della sessione. Lo stato sintetico per il tutor comprende tentativi ed eventi, non deduzioni arbitrarie dai clic.

Le sessioni del modello sono separate per sessione di studio. I giudizi vengono prodotti in una sessione Pi isolata. Le credenziali sono gestite dal runtime Pi e non inserite nel database didattico o nei messaggi. Gli strumenti di lettura/scrittura generici del coding agent, le estensioni e i file di contesto del workspace sono disabilitati nel tutor.

## Verifica

Dal progetto:

```sh
PYTHONDONTWRITEBYTECODE=1 <cartella dati>/.state/slides-runtime/bin/python -m unittest discover -s tests -p test_study.py -v
cd studio
npm test
npm run build
```

`npm test` verifica algoritmi, ponte HTML, FSRS e il vero SDK Pi attraverso un provider HTTP locale simulato. Non richiede credenziali e non misura la qualità di un modello commerciale.

I test Playwright richiedono un'istanza separata su dati fittizi, porta 4327; `STUDIO_TEST_URL` e `STUDIO_CHROME` permettono di specificare server e browser. Verificano percorso completo, ripresa, fonti, tastiera, indisponibilità del provider e modalità d'esame. Non vanno eseguiti sulla sessione personale di studio.

La verifica di ricerca sui materiali reali usa `tests/retrieval-cases.json` e `npm run verify:sources`, con `STUDIO_ROOT`, `STUDIO_PYTHON` e `STUDIO_PROJECT` configurati. Il rapporto viene salvato nella cartella dati, esclusa da Git.

## Limiti espliciti

Il percorso curato e verificato è PRAM/riduzione/scan. Gli altri percorsi sono creati dal modello e i loro giudizi non vengono promossi automaticamente a verifiche certe. Il tempo disponibile orienta il tutor, senza interrompere la sessione alla scadenza. Il corpus non assume che le date del programma di un anno precedente siano la data del prossimo esame.

La ricerca iniziale non usa embedding. I materiali mancanti, le trascrizioni parziali e i collegamenti candidati restano tali. Non è ancora inclusa esecuzione nativa CUDA, scrittura a mano o accesso remoto.

Il funzionamento tecnico può essere verificato subito; il miglioramento della preparazione richiede una sessione reale dello studente e una prova differita su problemi nuovi. I test con orologio simulato verificano il criterio temporale, non dimostrano apprendimento.
