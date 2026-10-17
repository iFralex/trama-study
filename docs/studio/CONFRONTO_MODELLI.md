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

Luna è il candidato da provare nelle letture ed estrazioni strutturate e nella selezione preliminare, mantenendo i validatori e il recupero dei casi incerti. Sol resta preferibile per riconciliare il programma, decidere il perimetro, produrre/revisionare capitoli e risolvere dubbi: è l’unico senza errori di classificazione in questo campione. Terra non offre un vantaggio misurato rispetto a Luna su questi compiti e non è automaticamente più economico di Sol: il suo equivalente API totale qui è superiore. L’app ha ancora un modello globale; questo confronto non ha introdotto instradamento automatico per fase.

I costi sopra sono stime dell’SDK alle tariffe API, non addebiti e non misure della percentuale consumata dell’abbonamento. Nel campione Luna ha un equivalente API circa 16,5 volte inferiore a Sol; questo rapporto non si può trasferire direttamente ai limiti ChatGPT. Le [indicazioni ufficiali sui limiti](https://learn.chatgpt.com/docs/pricing) distinguono consumo per modello, contesto, ragionamento, strumenti e cache, e riportano capacità indicative maggiori con Luna. Le [tariffe API](https://developers.openai.com/api/docs/pricing) sono separate. Vedi anche [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra) e [GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

Un solo passaggio per compito/modello non dimostra affidabilità statistica. Il campione tecnico è breve; non misura fedeltà di interi capitoli, efficacia didattica, HTML, uso degli strumenti o contesti lunghi. Risposte numeriche corrette e copia fedele non dimostrano che il modello possa sostituire tutte le fasi del tutor. I tempi includono le condizioni del servizio e non costituiscono una garanzia di velocità.

## Ripetere il confronto

`studio/server/compare-study-models.ts` genera solo un’anteprima per impostazione predefinita. Impostare `STUDIO_ROOT` alla cartella dati e usare `npm --prefix studio run compare:models -- --send` per inviare le richieste. `STUDIO_COMPARE_MODELS` seleziona gli ID separati da virgole, `STUDIO_COMPARE_REPORT` il rapporto. Il campione PDF è specifico del catalogo Parallel Computing corrente; se riservato, incompleto o non disponibile il programma si ferma prima dell’invio.

Il rapporto dettagliato, con risposte, errori, token e tempi, è conservato nella cartella dati `.state/studio/evaluations/model-comparison-20261017.json`, esclusa da Git. La correttezza delle annotazioni è stata ricontrollata sui casi falliti senza modificarle dopo i risultati. Typecheck TypeScript superato. Nessun contenuto delle fonti, risposta reale o credenziale aggiunto al repository.
