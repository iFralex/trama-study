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
