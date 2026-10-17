# Confronto dei modelli per il tutor — 17 ottobre 2026

Screening eseguito con il provider OpenAI e l’accesso ChatGPT già configurati, dopo il ripristino del limite. Il modello del corso non è stato cambiato e i risultati non entrano in piani, quesiti o tentativi dello studente.

| Modello | Classificazione | Verifiche tecniche | Estrazione PDF | Tempo totale | Token totali | Equivalente API stimato dall’SDK |
|---|---:|---:|---:|---:|---:|---:|
| GPT-6 Luna | 47/50 | 10/10 | 4/4 | 44,95 s | 5.243 | $0,001301 |
| GPT-5.6 Terra | 47/50 | 10/10 | 4/4 | 55,15 s | 5.270 | $0,030220 |
| GPT-6.1 Sol | 50/50 | 10/10 | 4/4 | 50,81 s | 4.783 | $0,021414 |
| GPT-5.4 mini | Non disponibile con questo accesso | — | — | — | — | — |

Sono nove richieste riuscite e una richiesta rifiutata. Il server rifiuta GPT-5.4 mini con errore 400: modello non supportato usando un account ChatGPT. La presenza nel catalogo locale di Pi non garantisce l’accesso effettivo. Questo risultato non è uno zero di accuratezza e non dipende dal limite appena ripristinato.

## Campione e metodo

Stesso livello di ragionamento `medium`, sessioni isolate, nessuno strumento, nessuna riparazione automatica. Modelli eseguiti in sequenza: Luna, Terra, mini, Sol. Nessuna lettura dalla cache nei conteggi restituiti. Il campione comprende:

- 30 classificazioni annotate di quesiti e 20 decisioni sintetiche sulle fonti, con il perimetro esplicito del benchmark, che include OpenMP introduttivo: non è il perimetro corrente del primo midterm 2025-26;
- 10 casi tecnici annotati: Amdahl, Gustafson, riduzione, prefix sum, EREW/CRCW, sincronizzazione CUDA, scansione sequenziale e semantica degli aggiornamenti paralleli;
- quattro sottopunti reali della pagina 5 del primo parziale dell’8 novembre 2022, verificata come non riservata e priva di intervalli protetti. Controlli su copia letterale, fonte, formato e pertinenza. Le soluzioni non vengono lette.

L’estrazione confronta il testo senza normalizzare operatori o correggere la domanda ambigua sulla sequential consistency. Tutti e tre i modelli funzionanti hanno copiato correttamente i quesiti e segnalato quell’ambiguità. Il benchmark non premia la modifica silenziosa del testo originale.

Luna sbaglia due formati (un problema misto classificato come codice e un calcolo classificato come aperto) e lascia incerto un contenuto amministrativo. Terra lascia incerta la pertinenza di tre domande incluse nel perimetro sintetico. Non si tratta di tre esclusioni definitive: nella pipeline lo stato incerto richiede approfondimento e consuma ulteriori risorse.

## Valutazione

Luna è il candidato da provare nelle letture ed estrazioni strutturate e nella selezione preliminare, mantenendo i validatori e il recupero dei casi incerti. Sol resta preferibile per riconciliare il programma, decidere il perimetro, produrre/revisionare capitoli e risolvere dubbi: è l’unico senza errori di classificazione in questo campione. Terra non offre un vantaggio misurato rispetto a Luna su questi compiti e non è automaticamente più economico di Sol: il suo equivalente API totale qui è superiore. Il confronto non ha modificato il modello globale. L’assegnazione automatica per fase è stata implementata successivamente, su richiesta dello studente: vedi la sezione Luna/Sol nella [guida della preparazione](PREPARAZIONE_VERIFICABILE.md).

I costi sopra sono stime dell’SDK alle tariffe API, non addebiti e non misure della percentuale consumata dell’abbonamento. Nel campione Luna ha un equivalente API circa 16,5 volte inferiore a Sol; questo rapporto non si può trasferire direttamente ai limiti ChatGPT. Le [indicazioni ufficiali sui limiti](https://learn.chatgpt.com/docs/pricing) distinguono consumo per modello, contesto, ragionamento, strumenti e cache, e riportano capacità indicative maggiori con Luna. Le [tariffe API](https://developers.openai.com/api/docs/pricing) sono separate. Vedi anche [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra) e [GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

Un solo passaggio per compito/modello non dimostra affidabilità statistica. Il campione tecnico è breve; non misura fedeltà di interi capitoli, efficacia didattica, HTML, uso degli strumenti o contesti lunghi. Risposte numeriche corrette e copia fedele non dimostrano che il modello possa sostituire tutte le fasi del tutor. I tempi includono le condizioni del servizio e non costituiscono una garanzia di velocità.

## Ripetere il confronto

`studio/server/compare-study-models.ts` genera solo un’anteprima per impostazione predefinita. Impostare `STUDIO_ROOT` alla cartella dati e usare `npm --prefix studio run compare:models -- --send` per inviare le richieste. `STUDIO_COMPARE_MODELS` seleziona gli ID separati da virgole, `STUDIO_COMPARE_REPORT` il rapporto. Il campione PDF è specifico del catalogo Parallel Computing corrente; se riservato, incompleto o non disponibile il programma si ferma prima dell’invio.

Il rapporto dettagliato, con risposte, errori, token e tempi, è conservato nella cartella dati `.state/studio/evaluations/model-comparison-20261017.json`, esclusa da Git. La correttezza delle annotazioni è stata ricontrollata sui casi falliti senza modificarle dopo i risultati. Typecheck TypeScript superato. Nessun contenuto delle fonti, risposta reale o credenziale aggiunto al repository.


## Confronto del flusso reale: Sol oppure Luna/Sol

Su richiesta dello studente, la preparazione è stata messa in pausa prima del confronto. La prima modalità ibrida rileggeva spesso l’intero compito con Sol dopo Luna; le misure operative non dimostravano un risparmio rispetto a una sola passata Sol. Il nuovo confronto usa invece gli stessi testi, stesso perimetro, stesso prompt circoscritto, ragionamento medium e nessuno strumento per entrambe le strategie. Il misto aggiunge Sol solo per gli intervalli che Luna propone di escludere; tutte le chiamate sono contate.

Campione: 15 intervalli reali non riservati, annotati prima delle richieste, dalle registrazioni del 16 settembre al 4 novembre. Include PRAM, scaling, memoria, data parallel, trascrizioni danneggiate, logistica e PCAM escluso. Due ripetizioni per strategia, ordine alternato. Gli insiemi di stati ammissibili distinguono un dubbio conservativo da un’esclusione errata; nessuna annotazione è stata cambiata dopo le risposte.

La prima versione del contesto ometteva le motivazioni del perimetro e non distingueva abbastanza gli algoritmi comuni a più blocchi: entrambe le strategie hanno scartato lo scan CUDA/PRAM come pattern escluso. Sol: 28/30 decisioni accettabili, misto: 26/30; entrambe con due omissioni critiche nelle ripetizioni. Quella versione è stata scartata. La correzione conserva il summary completo dell’obiettivo e richiede di mantenere il dubbio quando l’algoritmo può appartenere sia a un blocco incluso sia a uno escluso. Il difetto era anche nel contesto, non soltanto nella capacità del modello.

Confronto ripetuto dopo questa correzione:

| Strategia | Decisioni accettabili | Omissioni critiche | Chiamate | Tempo delle richieste | Equivalente API stimato |
|---|---:|---:|---:|---:|---:|
| Solo Sol | 30/30 | 0 | 4 | 54,80 s | $0,077248 |
| Luna + verifica mirata Sol | 30/30 | 0 | 8 | 84,43 s | $0,052001 |

Il misto costa il **32,7% in meno nella selezione di questo campione**, includendo tutte le verifiche; è più lento. Non è una stima del risparmio su tutta la preparazione o della percentuale dell’abbonamento. I 30 casi sono 15 passaggi ripetuti, non 30 fonti indipendenti. Il prompt è stato corretto sul primo campione: le ripetizioni misurano la regressione, non dimostrano generalizzazione. Non sono stati generati capitoli durante questo confronto.

Validazione aggiuntiva su sei pagine PDF originali non utilizzate nella correzione del prompt: politiche concurrent write PRAM, modello CUDA host/device, memory fences nei modelli relaxed, API Pthreads, direttive OpenMP e metodologia PCAM. Annotazioni fissate prima delle richieste, un solo passaggio per strategia, nessuna ulteriore modifica del prompt. Entrambe superano 6/6 senza omissioni critiche. Solo Sol: una chiamata, 11,20 s, $0,015404; misto: due chiamate, 18,28 s, $0,012954: **15,9% in meno**. Questo campione ha più esclusioni e mostra che il vantaggio dipende dalla composizione delle fonti.

Combinando confronto corretto e validazione: **36/36 decisioni accettabili per strategia**, su 21 intervalli unici; costo equivalente $0,092652 con Sol e $0,064954 con il misto, circa **29,9% in meno**. L’esito resta limitato a questi compiti e non misura l’autonomia dello studente o l’utilizzo effettivo dell’abbonamento.

Scelta implementata: **Luna soltanto per selezione circoscritta; Sol per lettura tecnica, quesiti d’esame, dubbi, mappa, contenuti, chat e tutte le revisioni**. Non si estende a tutta l’estrazione un vantaggio misurato solo sulla selezione. Le fonti incerte restano incluse e vengono approfondite da Sol. I documenti già sistematicamente esclusi passano direttamente a Sol; la proposta valida di Luna sopravvive alle interruzioni della verifica. I checkpoint completati della preparazione restano invariati.

Esecuzione ripetibile: `STUDIO_ROOT=/percorso/dati npm --prefix studio run compare:routing -- --send`; senza `--send` salva soltanto l’anteprima locale. `--validation` usa sei pagine PDF differenti, annotate prima delle nuove richieste. La procedura verifica localmente riserva, soluzioni e intervalli protetti prima di leggere o inviare ciascuna fonte; non modifica impostazioni o progressi. I rapporti privati sono nella cartella dati `.state/studio/evaluations/`: `routing-comparison-20261017.json` (prima versione rifiutata), `routing-comparison-v2-20261017.json` (confronto corretto) e `routing-validation-20261017.json` (validazione aggiuntiva). Testi e risposte restano fuori da Git.
