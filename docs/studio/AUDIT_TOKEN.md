# Audit dei token di Studio — 26 ottobre 2026

Analisi del codice e del database locale in sola lettura. Nessuna nuova richiesta al modello, modifica dei prompt in produzione o interruzione della preparazione. Le dimensioni qui sotto sono **caratteri JSON compatti**, non token fatturati. Le richieste storiche includono versioni precedenti e tentativi falliti: non rappresentano tutte il comportamento corrente.

## Cosa significa conservare il risultato

Per un modello generativo non è dimostrabile che un prompt diverso produca le stesse parole. È invece verificabile che un'ottimizzazione conservi integralmente i dati, le versioni, le relazioni, le istruzioni necessarie e tutti i controlli applicati al risultato. Le ottimizzazioni senza perdita vanno separate da selezione del contesto, riassunti, cambi di modello o eliminazione di revisioni, che possono modificare le conclusioni.

## Opportunità con conservazione integrale dei dati

| Intervento | Evidenza locale | Come conservarne il significato | Priorità |
| --- | --- | --- | --- |
| Rappresentare una sola volta i testi identici delle fonti | Nell'ultimo tentativo esaminato il payload del valutatore contiene 23.174 caratteri; 4.501 caratteri di testo delle fonti ricorrono più volte fra fonti dirette e pagine di contesto | Registro di fonti con riferimenti alle stesse pagine, conservando ordine, metadati, qualità, citazioni, revisioni e ricevute di lettura. Nessuna deduplicazione di testi diversi con lo stesso ID | Alta |
| Evitare di ripetere il capitolo corrente dentro e fuori dal piano | Nell'ultimo compito `chapter`, l'oggetto `chapter` di 9.400 caratteri è identico alla voce corrispondente di `plan.data.chapters` | Un solo oggetto e un riferimento esplicito. Ricostruzione locale del vecchio oggetto esattamente uguale per confronto automatico | Alta |
| Tenere i dati tecnici del checkpoint fuori dal testo inviato al modello | `task_id`, `model_key`, `budget`, `source_revisions` pesano circa 2.627 caratteri nelle revisioni e 5.089 nel compito di scrittura esaminato | Conservare integralmente il task originale nel servizio per identità, integrità e commit; inviare un distinto pacchetto semantico. Non eliminare limiti didattici o strutturali come `chapter_limits` | Media |
| Riutilizzare letture identiche all'interno della stessa sessione del revisore | `read_source` restituisce sempre il passaggio più due pagine vicine; può ripetere dati presenti nell'input o in una lettura precedente | Risposte con riferimenti a testo già consegnato, soltanto per stessa sessione e stessa revisione. Se quel testo non è più nel contesto attivo, restituirlo per intero. Conservare la registrazione della lettura | Media; richiede integrazione con il contesto attivo dell'SDK |

I risparmi delle righe non si possono sommare come percentuali globali: riguardano fasi e campioni diversi. Anche il risparmio economico dipende da quali token il provider considera già in cache.

## Opportunità più grandi, da verificare prima di applicare

**Stato reinviato nella chat.** `Tutor.chat` conserva la conversazione tramite `SessionManager.continueRecent` e aggiunge a ogni turno lo stato completo. Lo stato corrente esaminato è di 329.835 caratteri: 159.947 nel piano, 52.825 nel capitolo corrente e 39.499 nel profilo d'esame, oltre a obiettivo, diario, tentativi ed eventi. Questo non significa che tutti siano inutili. Una fotografia iniziale più aggiornamenti versionati può evitare molte ripetizioni senza riassumere i contenuti. Occorre però gestire modifiche del piano, cambio capitolo, nuove valutazioni, correzioni del diario, riapertura della sessione e compattazione dello storico. Finché questa ricostruzione non è verificata, togliere semplicemente lo stato dai messaggi rischia regressioni.

**Istruzioni specifiche per ruolo.** Autore e revisori ricevono il lungo prompt del tutor, che descrive anche conversazione, avanzamento, creazione di attività e diario. Molti di questi strumenti non sono disponibili nei ruoli di preparazione. Conviene separare le sole istruzioni di interazione dalle regole comuni su fonti, privacy, perimetro, notazione e didattica. È una modifica delle istruzioni: richiede confronti sul comportamento, non basta verificare il JSON.

**Profilo d'esame e piano.** I compiti delle revisioni ricevono un profilo di circa 39.500 caratteri. La scrittura riceve l'intero piano, di circa 160.000 caratteri. Selezionare solo quesiti o capitoli pertinenti può risparmiare molto, ma la pertinenza è una decisione: non equivale a eliminare una duplicazione. Va mantenuta la possibilità di confrontare prerequisiti, perimetro e formato dell'esame. Non lo considero un risparmio dimostrato senza perdita.

**Risoluzione indipendente degli esercizi.** Il meccanismo di checkpoint per blocco può essere esteso alle soluzioni del revisore, per non rifare quelle completate dopo un timeout. Bisogna mantenere nascosta la soluzione dell'autore, preservare il contesto delle dipendenze e verificare che ogni attività sia stata risolta. Suddividere ingenuamente in nuove sessioni con tutto il capitolo reinviato potrebbe aumentare i token di ingresso.

## Cosa è già ottimizzato

- La consegna di un esercizio genera la valutazione breve isolata; la spiegazione estesa parte su richiesta.
- Una valutazione già salvata viene riutilizzata senza una nuova correzione.
- La correzione del capitolo usa sostituzioni dei blocchi interessati e checkpoint persistenti.
- Selezione e verifica delle esclusioni usano pacchetti circoscritti; i risultati validi del lettore possono sopravvivere a un'interruzione dell'esperto.
- I contributi alla mappa e la riconciliazione non ricevono strumenti inutili; alcune strutture sono già ridotte a inventari o fatti recuperabili.
- I JSON inviati dal server sono già compatti: eliminare spazi di formattazione dall'input non offre un ulteriore risparmio significativo.

## Vincoli e verifica per l'implementazione

1. Per deduplicazione e pacchetti, confrontare l'espansione del nuovo formato con il vecchio payload: testi, strutture e relazioni devono coincidere senza tagli.
2. Conservare i task originali, i controlli di provenienza e aggiornamento delle fonti, i limiti, i modelli deterministici e le revisioni indipendenti.
3. Verificare in particolare pagine condivise, fonti con revisioni differenti, ripresa dopo interruzione, cambio capitolo e compattazione della conversazione.
4. Misurare richieste complete, incluse letture successive, ritentativi e token di cache. Un primo prompt più piccolo non dimostra un risparmio totale.
5. Per cambiamenti alle istruzioni o selezione del contesto, confrontare accuratezza delle correzioni, citazioni, completezza didattica e comportamento degli strumenti. I soli test strutturali non possono escludere regressioni delle risposte generate.

Prima applicazione consigliata: deduplicazione esatta delle fonti e del capitolo corrente, poi separazione dei metadati locali. La gestione degli aggiornamenti della chat è il candidato più grande, ma richiede un intervento più articolato.
