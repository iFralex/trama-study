# Studio: tutor locale con Pi

Apri `Studio.command`, oppure `Avvia.command` → operazione 5. Il browser si apre su `http://127.0.0.1:4326`. Lascia aperto il terminale; Ctrl+C ferma il servizio. Il primo avvio prepara e compila l'interfaccia. Node.js 22+ e il runtime visivo Python sono necessari. Dipendenze, cache, conversazioni e database seguono la cartella dati configurata.

Scegli il corso e premi **Riprendi il percorso**. Una sessione precedente conserva attività, versione, bozze, interazioni e tentativi. **Nuova sessione** conserva lo storico. Obiettivo e tempo si modificano nella sessione. **Modello e accesso** elenca i modelli autenticati e offre i flussi API/OAuth dei provider Pi. Il programma non presuppone che un abbonamento dia accesso a ogni modello. Le fonti recuperate e le risposte necessarie vengono inviate al provider scelto; i file originali restano sul disco.

## Prima versione

- Chat Markdown/LaTeX con attività incorporate e pannello espandibile.
- Importazione incrementale, basata su SHA-256, di PDF, notebook, trascrizioni e allineamenti. Nessuna esecuzione dei notebook.
- Ricerca ibrida FTS5 + embeddings multilingue locali ONNX, con contesto e riferimenti a pagina/cella/timestamp. Indicizzazione incrementale e riprendibile.
- Navigazione dei file, ricerca letterale anche nel codice e lettura di intervalli di righe, senza shell. Sono indicizzati anche HTML, Markdown e file sorgenti testuali.
- Sezione **Sessioni**: ricerca delle conversazioni e ripresa esatta. Il tutor può consultare sessioni precedenti quando richiesto.
- Ricerca web e lettura di pagine/PDF primari quando le fonti del corso non bastano, con provenienza distinta.
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

I materiali mancanti, le trascrizioni parziali e i collegamenti candidati restano tali. Non è ancora inclusa esecuzione nativa CUDA, scrittura a mano o accesso remoto.

Il funzionamento tecnico può essere verificato subito; il miglioramento della preparazione richiede una sessione reale dello studente e una prova differita su problemi nuovi. I test con orologio simulato verificano il criterio temporale, non dimostrano apprendimento.

## Collegare ChatGPT

Apri **Modello e accesso → Collega ChatGPT**, completa l'accesso nel browser e scegli un modello disponibile → **Usa questo modello**. Viene usato l'OAuth del provider `openai` di Pi, con API pubblica OpenAI e flusso Sign in with ChatGPT; non il provider legacy `openai-codex`. L'idoneità e i modelli dipendono dall'account; il collegamento non importa le tue conversazioni ChatGPT. La chiave API resta una modalità separata. [Documentazione ufficiale](https://developers.openai.com/siwc/quickstart).

## Ricerca, memoria e fonti incerte

Il modello locale è `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, FastEmbed 0.7.4, ONNX CPU a due thread, 384 dimensioni. Non serve un'API di embeddings. Ambiente, modello e indice risiedono nel disco dati: `.state/embeddings-runtime`, `.state/embedding-models` e `.state/studio/studio.sqlite3`. Il primo caricamento scarica il modello. Mentre si prepara, rimane disponibile la ricerca testuale. La sezione Fonti mostra lo stato.

I passaggi vengono suddivisi per token con sovrapposizione; gli embeddings conservano il riferimento al passaggio originale. Il risultato cita sempre la pagina o l'intervallo, non una ricostruzione del modello. I batch vengono salvati atomicamente e ricalcolati solo quando cambia il testo o l'identità del modello. I temi riservati non compaiono negli strumenti di ricerca; durante la simulazione anche lo storico è escluso dal tutor.

Gli strumenti `list_materials`, `grep_materials`, `read_material` permettono di elencare file, cercare testo letterale e leggere righe con ID citabili. `search_sessions` e `read_session` recuperano messaggi, attività e tentativi senza cambiare la sessione corrente. La ricerca parte dal corso/anno corrente; si estende ad altri corsi solo su richiesta esplicita. Le sessioni rimangono salvate in SQLite e le conversazioni Pi in `.state/studio/pi`.

Politica concordata: prima confrontare le fonti del corso; usare conoscenza interna dichiarata solo per fatti elementari e stabili; verificare online negli altri casi. Le formulazioni esterne vanno confrontate per variabili, ipotesi, convenzioni e profondità. Se l'equivalenza rimane irrisolta, il tutor deve mostrare il confronto e chiedere chiarimenti prima di continuare quella spiegazione. Questa è un'istruzione al modello, non una garanzia matematica di correttezza: i giudizi aperti rimangono provvisori.

La ricerca web pubblica usa DuckDuckGo con fallback Bing RSS, senza chiavi aggiuntive; può essere limitata dai siti. `read_web_page` legge HTML o PDF, salva URL, momento e testo in `.state/studio/web`, e conserva le verifiche TLS. Limiti: HTTPS pubblico, 3 MB per risposta, 24.000 caratteri, fino a 12 pagine PDF per lettura (parametro `page` per proseguire). Le query devono contenere termini tecnici generici, senza informazioni personali o trascrizioni. In caso di indisponibilità il tutor deve dichiararla. I file originali non vengono corretti né riscritti.

Per ripetere la verifica semantica e ibrida sul corso reale, usa `npm run verify:embeddings` con le stesse variabili della verifica delle fonti. Il rapporto viene scritto in `.state/studio/hybrid-verification.json`.

## Tema chiaro e scuro

Il pulsante **Tema scuro / Tema chiaro** in alto a destra cambia il tema senza interrompere le attività. La preferenza viene ricordata nel browser; al primo accesso si segue il tema del sistema. Chat, formule, pannelli e attività HTML condividono il tema. I PDF conservano i colori originali.

## Partire dalle basi

**Parti dalle basi** avvia un percorso ordinato sulle lezioni del corso, con prerequisiti, spiegazioni, esempi svolti e prove guidate/autonome. Argomenti e attività sono ancorati alle fonti; lezione, argomento e fase rimangono salvati. [Guida e limiti del percorso](DALLE_BASI.md).

## Formule matematiche

Chat e attività testuali renderizzano LaTeX con KaTeX: `$...$` e `\(...\)` inline, `$$...$$` e `\[...\]` in blocco. La normalizzazione avviene solo nella visualizzazione: messaggi salvati, codice e destinazioni dei collegamenti rimangono invariati.

## Lettura delle formule sotto il puntatore

In alto, **Accessibilità** offre tre modalità persistenti:

- **Formula intera** (predefinita): la formula rimane visivamente identica; un vero testo italiano, non una sola etichetta ARIA, copre la stessa area ai fini della lettura sotto il puntatore. La parte grafica non espone singoli simboli all'albero accessibile.
- **Esplora i simboli**: ripristina il MathML originale di KaTeX per la navigazione strutturale.
- **Testo leggibile**: mostra la descrizione in parole come un singolo testo, utile se la lettura sotto il puntatore di macOS ignora l'etichetta del ruolo matematico.

Le descrizioni sono calcolate sul Mac da Speech Rule Engine 4.1.4, su MathML prodotto da KaTeX, senza modelli AI o servizi esterni. Frazioni, potenze e pedici mantengono una lettura strutturale; non viene modificata né interpretata come una diversa formula la fonte originale. La pronuncia non sostituisce una spiegazione del significato. Il backend mantiene una cache in memoria; le descrizioni vocali e le preferenze non vengono aggiunte alla cronologia del tutor.

Le verifiche browser controllano l'oggetto matematico unico nell'albero accessibile, il puntatore sulla `n`, la presenza di un unico elemento StaticText con l'intera descrizione, la coincidenza delle dimensioni con la formula e la resa visiva, le alternative e la preferenza dopo il ricaricamento. La voce nativa **Leggi gli elementi sotto il puntatore** deve essere provata sul Mac dell'utente: i test browser non garantiscono il comportamento di ogni versione di macOS/browser. Riferimenti: [KaTeX e MathML](https://katex.org/docs/options), [nome accessibile delle espressioni matematiche](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/math_role).
