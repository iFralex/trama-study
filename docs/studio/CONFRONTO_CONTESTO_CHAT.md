# Misura del risparmio e verifica del contesto della chat

26 ottobre 2026. Modello: quello configurato in Studio, OpenAI `gpt-6.1-sol`, ragionamento medium. Contesto reale del corso letto tramite SQLite `mode=ro`; invio autorizzato esplicitamente dall'utente. La valutazione iniziale è stata eseguita su un prototipo isolato, senza modificare tentativi, preferenze, diario o piano dell'utente. L'attivazione successivamente richiesta è descritta nella sezione finale.

## Le tre ottimizzazioni già attive

Misure sui soli dati JSON dei pacchetti reali. I token della tabella sono stime locali dell'SDK, non conteggi del provider sull'intera richiesta.

| Fase | Token stimati prima | Dopo | Risparmio del payload |
| --- | ---: | ---: | ---: |
| Scrittura capitolo | 74.268 | 70.187 | 5,5% |
| Correzione mappa | 64.859 | 62.265 | 4,0% |
| Revisione didattica | 47.942 | 47.272 | 1,4% |
| Valutazione esercizio | 5.831 | 4.736 | 18,8% |

Questi numeri non includono istruzioni di sistema, strumenti e risposta. Non si possono mediare per stimare il risparmio mensile senza sapere quali richieste vengono eseguite e quali token risultano già in cache.

## Prototipo di chat confrontato

La versione compatta mantiene integralmente capitolo corrente, obiettivo e confini dell'esame, diario, preferenze, tentativi, interazioni e problemi aperti del piano. Sostituisce i dettagli dei capitoli del piano con un indice e sposta i testi dei quesiti dietro uno strumento di lettura. `read_context` restituisce capitoli integrali, quesiti paginati o tutto lo stato come fallback. Non vengono generati riassunti con un altro modello.

Il contesto attuale era di 350.365 caratteri; il primo prototipo lo riduceva a 232.641: **33,6% in meno nel messaggio iniziale**. Il precedente campione da circa 330.000 caratteri era una fotografia antecedente del percorso: lo stato varia con nuovi tentativi e contenuti.

## Confronto principale: sei casi, due strategie

Due sessioni nuove per strategia, tre turni per sessione. Stesso snapshot e stesso modello. L'ordine delle strategie è invertito fra le due sessioni. Le preferenze modificate durante l'esperimento sono sintetiche e non vengono salvate nel corso.

I casi verificano: distinzione T*/T1 nelle metriche; esclusione attuale di OpenMP rispetto ai temi storici; trascrizione esatta dell'assessment di un altro capitolo e dei suoi primi due riferimenti; preferenza corrente; rettifica della preferenza; rifiuto di inventare un T* numerico senza dati.

| Indicatore | Stato completo | Prototipo compatto |
| --- | ---: | ---: |
| Casi con campi richiesti corretti | 6/6 | 6/6 |
| Letture aggiuntive con strumenti | 2 | 2 |
| Risposte del modello, incluse continuazioni dopo strumenti | 8 | 8 |
| Token registrati, incluso cache read | 1.647.258 | 1.171.956 |
| Token di input non in cache registrati | 821.729 | 439.456 |
| Tempo totale | 156,8 s | 76,5 s |
| Compattazioni dello storico | 2 | 0 |
| Costo equivalente stimato dall'SDK sulle risposte registrate | 2,247789 | 0,9631312 |

Nel campione: **28,9% di token registrati in meno**, **46,5% di input non in cache in meno**, **51,2% di tempo totale in meno**. Il costo equivalente dell'SDK sulle risposte registrate diminuisce del **57,2%**; non è una misura degli addebiti né della quota dell'abbonamento.

Importante limite contabile: il primo runner registrava l'evento di compattazione ma non la sua usage separata. I token e il costo delle due compattazioni della versione completa non sono inclusi nella tabella; la compatta non ha compattazioni. Il vantaggio numerico sulle sole risposte è quindi una misura prudente, ma non un totale completo di tutte le chiamate. Non si presume un costo nullo per la compattazione. Il runner è stato corretto per raccogliere anche questa usage nelle prove successive.

## Qualità: un'anomalia osservata e una validazione incompleta

Il controllo dei campi non basta a dimostrare assenza di regressioni. La revisione delle risposte ha trovato una differenza secondaria: nel caso OpenMP, il primo prototipo ha aggiunto che il perimetro era una sintesi «da confermare», riprendendo una frase storica del summary benché `objective.confirmed` fosse già true. La conclusione sull'esclusione di OpenMP restava corretta. La versione completa, in quel confronto, non ha aggiunto il caveat. Una singola esecuzione non dimostra che la differenza sia causata dalla compressione, ma è comunque un problema osservato, da non nascondere dietro il 6/6.

Il prototipo è stato aggiornato con fatti di stato espliciti: conferma corrente e versione del piano, oltre a un'impronta del profilo per invalidare quesiti vecchi. Una conferma assente rimane sconosciuta, non diventa false. I campi strutturati attuali prevalgono sulle vecchie frasi narrative. Il test aggiuntivo sullo stato confermato è passato per entrambe le versioni, con spiegazioni coerenti. È una verifica mirata, non la prova che il caveat non possa ripresentarsi con altre domande.

La validazione aggiuntiva prevedeva anche il recupero letterale di un quesito e la sua rettifica fra turni. La versione completa ha superato entrambi. Nella versione compatta il modello ha chiamato lo strumento per recuperare il quesito, ma prima della risposta finale OpenAI ha segnalato `Subscription Sharing usage limit`. Il runner ha fermato le richieste: **questo caso è non valutabile per quota**, e la rettifica successiva non è stata eseguita. Non sono né due regressioni accertate né due casi riusciti. I totali delle strategie in questa prova incompleta non vengono usati per calcolare percentuali comparative.

In questa seconda prova la compattazione della versione completa ha richiesto separatamente 233.215 token, raccolti correttamente dal runner aggiornato: conferma che ignorarla sottostimerebbe il consumo. Non si può attribuire questo stesso numero alle compattazioni del primo confronto.

## Limiti e decisione

- Il campione è piccolo: sette casi hanno un confronto completo fra le strategie, sei nel test principale e uno nella validazione. Non fornisce una probabilità di regressione.
- Il confronto usa il prompt di sistema del tutor, ma espone solo letture del contesto e delle fonti. Non verifica tutti i flussi di scrittura, adattamento del piano, HTML, recupero della conversazione o insegnamento lungo.
- Lo snapshot e alcune richieste sono molto estesi. Cache, compattazione e soglie di prezzo presenti nei metadati SDK influenzano il costo; le percentuali non si applicano automaticamente a ogni conversazione.
- Il recupero del profilo d'esame aggiornato rimane da validare con il modello. I test locali ne verificano ricostruzione senza perdita, paginazione, stato corrente e guardie per prove autonome.
- Il provider ha raggiunto il limite durante il confronto. Nessun'altra richiesta al modello viene eseguita per completare il campione senza una nuova disponibilità della quota.

Esito della valutazione iniziale: risparmio promettente e misurato; il prototipo era rimasto isolato in attesa della decisione dell'utente. La verifica con il modello dei due casi incompleti e di sessioni più lunghe rimane un limite della valutazione, anche dopo l'attivazione richiesta dall'utente.

## Riproduzione e artefatti

`npm run compare:chat-context` genera un'anteprima senza chiamate al modello, usando dati sintetici. Il confronto reale richiede esplicitamente `--real-context --allow-real-data --send` e `STUDIO_ROOT`, dopo autorizzazione all'invio dei dati; `--validation` esegue il gruppo aggiuntivo. Il runner disabilita i tentativi automatici e interrompe il confronto quando rileva un limite d'uso.

I report privati, esclusi da Git, sono `.state/evaluations/chat-context-real.json` e `.state/evaluations/chat-context-real-validation.json`. Contengono usage, tempi, letture, risposte, campi attesi ed errori. L'equivalente complessivo ai prezzi nei metadati SDK delle due prove registrate è circa 5,22, escluso il costo non raccolto delle prime due compattazioni: non è l'importo addebitato né una misura dell'abbonamento.

Verifica locale conclusiva: suite completa da 63 test passata; i cinque test mirati del prototipo, incluso il successivo caso di conferma assente, sono passati. Controllo TypeScript riuscito. Questa era la verifica del prototipo prima dell'integrazione.


## Attivazione nell'app richiesta dall'utente

La chat del percorso ora usa `chat-context.ts` per il messaggio iniziale di ogni turno. Anche `get_context` e `get_course_plan` restituiscono i dati correnti in forma compatta, evitando di reinviare automaticamente il piano completo. `read_context` recupera un capitolo integrale del piano oppure tutto lo stato; per i quesiti usa la stessa lettura del profilo del backend, paginata da dieci, e può quindi proseguire oltre i venti quesiti inclusi nella fotografia iniziale.

Ogni lettura ricarica lo stato della sessione: conferme, versioni del piano, cambi di capitolo e rettifiche vengono aggiornati. Le istruzioni del tutor impongono di recuperare i dettagli prima di usarli e il piano integrale prima di modificarlo. Le guardie su esami e richiami sono applicate anche alle letture. Lo storico delle sessioni esistenti rimane disponibile, quindi i vecchi messaggi con stato esteso possono ancora occupare contesto fino alla normale compattazione.

L'integrazione non altera i pacchetti isolati di valutazione degli esercizi o le sessioni di preparazione. Il nuovo strumento viene esposto soltanto al tutor dei percorsi. Il test SDK di produzione copre contesto iniziale, aggiornamenti di contesto e piano, recupero integrale, venticinque quesiti, riapertura della sessione, cambio capitolo, nuova versione del piano, rettifica di un quesito e blocco del richiamo. Usa un server modello locale simulato e non consuma quota OpenAI. I limiti della valutazione generativa precedente restano quelli descritti sopra.

Verifica dell'integrazione attiva: **65 test passati**, controllo TypeScript e build riusciti. In questa fase sono state usate soltanto risposte simulate su server locale, senza ulteriori richieste a OpenAI.
