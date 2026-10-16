# Associare slide e materiali alle lezioni

Avvia `Avvia.command`, scegli il corso e l’operazione **4) Associa slide e materiali alle lezioni**. Nel menu dopo un download è l’operazione 7; nel menu avanzato è la 10. Non occorre aprire WeBeep. Scarica prima lezioni e materiali del corso.

Puoi analizzare tutte le lezioni, la prima per prova o selezionare numeri/intervalli. Le analisi complete vengono verificate e saltate. Ctrl+C interrompe: ripeti la stessa selezione per riutilizzare le scansioni, le schermate riconosciute e i confini già salvati. Una scansione in corso riparte al massimo dall’ultima finestra di 10 minuti non completata. File di uscita alterati vengono ricostruiti dai checkpoint. Non vengono modificati video, PDF, notebook o trascrizioni originali.

## I quattro passaggi

1. **Indice dei materiali**: PyMuPDF estrae e rende le pagine PDF; Tesseract legge le pagine prive di testo. Le celle `.ipynb` sono lette come JSON, senza eseguire codice. L’indice è nella cartella del corso, `indice-materiali/index.json`; conserva pagina PDF a partire da 1 e, se trovato, numero stampato. Altri formati, link HTML e archivi non sono indicizzati.
2. **Cambi schermata**: PyAV decodifica il video, OpenCV cerca la zona della presentazione e rileva le differenze visive ogni 2 secondi. I tempi usano i PTS dei fotogrammi, anche a frame rate variabile. Le schermate più brevi del passo di campionamento possono sfuggire; piccoli cambi, animazioni e ritagli automatici restano limiti del rilevatore.
3. **Riconoscimento**: testo OCR e hash percettivo recuperano le pagine candidate; ORB, omografia RANSAC e confronto dei bordi verificano la geometria. I punteggi sono indicatori euristici, non probabilità calibrate. Figure duplicate tra documenti restano ambigue se le prove non le distinguono. Il nome del notebook visibile consente un’associazione al documento: le celle suggerite dal testo restano candidate, non confermate.
4. **Confini**: nei dintorni di ogni cambio rilevato si confrontano i singoli fotogrammi e si salva l’incertezza locale. Questa precisione non certifica né l’identità della pagina né l’assenza di cambi sfuggiti alla scansione.

## Risultati

Ogni lezione ha una cartella `allineamento` con:

- `allineamento.md`: tabella leggibile degli intervalli.
- `allineamento.csv`: intervalli, materiale, pagina e incertezze.
- `allineamento.json`: tutte le prove, alternative, OCR e segmenti di trascrizione associati.
- `sessioni`: fotogrammi di prova e checkpoint di ripresa.
- `completo.json`: identità delle sorgenti e checksum delle uscite.

Gli stati sono `matched` (pagina PDF riconosciuta), `ambiguous` (alternative), `document_only` (notebook riconosciuto, celle candidate), `unknown` (nessuna corrispondenza sicura). Il JSON conserva il testo e i timestamp originali dei segmenti Whisper e ne indica l’intersezione con la slide. Un segmento che attraversa un cambio compare in entrambi gli intervalli: non sono inventati timestamp parola per parola. Anche trascrizioni parziali possono essere associate; dopo averle completate, riesegui l’analisi per aggiornare il testo senza rifare il lavoro visivo. La qualità del testo Whisper non viene corretta da questo processo.

## Ambiente e comandi

Gli strumenti visivi usano un ambiente separato nella cartella dati, `.state/slides-runtime`, con le versioni in `requirements-slides.txt`. Il Python dell’app non viene migrato. Servono Python 3.12 nativo (`brew install python@3.12`) e Tesseract (`brew install tesseract`). Al primo utilizzo le librerie Python vengono installate automaticamente. Dati, cache e file temporanei di questa funzione rimangono sul disco dati. Installazione iniziale e successivi cambi dei materiali richiedono nuovo lavoro; l’analisi ordinaria è locale.

Dalla cartella dell’app:

```bash
.venv/bin/python -m polimi_lectures.cli align --course "nome corso" --all
.venv/bin/python -m polimi_lectures.cli align --course "nome corso" --index-only
.venv/bin/python -m polimi_lectures.cli align --course "nome corso" --lesson-id ID --start 1200 --end 1900
```

Le prove su intervalli sono salvate in `allineamento/prove`, senza sostituire l’analisi completa. `--step 0.5` aumenta il campionamento; `--crop X Y W H` imposta manualmente la zona del video; `--pdf nome.pdf` limita i PDF candidati (ripetibile), utile solo quando si conosce già il documento. Queste scelte fanno parte dell’identità della sessione e richiedono una nuova analisi. Non forzare un PDF per nascondere ambiguità reali.

Test visivi separati dalle dipendenze dell’app:

```bash
TMPDIR="/percorso/disco/dati/.state/slides-tmp" /percorso/disco/dati/.state/slides-runtime/bin/python -m unittest discover -s tests -p test_slides.py -v
```

## OCR alla risoluzione originale

Il riconoscimento legge ora i fotogrammi alla risoluzione originale, senza il precedente limite OCR a 1100 pixel. Il limite rimane solo per il confronto geometrico, separato dall’OCR. Nei notebook individua il titolo attivo e legge il contenuto sotto la barra strumenti, mantenendo i pixel originali ed escludendo i commenti HTML invisibili dal confronto. Le celle restano candidate. La versione 2 del riconoscitore aggiorna automaticamente i vecchi risultati riutilizzando scansioni e fotogrammi verificati; non è necessario riscaricare le lezioni.
