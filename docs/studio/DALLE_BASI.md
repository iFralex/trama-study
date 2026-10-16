# Studiare dalle basi, seguendo le lezioni

Premi **Parti dalle basi** nella schermata iniziale o in una sessione standard. Viene creata una sessione dedicata; il tutor legge le fonti della prima lezione e propone un piano. **Riprendi il percorso** e **Sessioni** riaprono il punto già salvato. Serve un modello collegato: se il provider non risponde, la sessione e la richiesta rimangono salvate; **Riprendi la spiegazione** consente di ritentare.

Il pannello del percorso permette di scegliere lezione e argomento e mostra fase, obiettivo e prerequisiti. Non serve digitare ogni volta che non si conosce l'argomento. **Programma** elenca le lezioni disponibili, nell'ordine delle fonti. È sempre possibile cambiare direzione, chiedere un esempio più semplice o vedere una soluzione.

## Come vengono scelti gli argomenti

Con trascrizioni disponibili, il percorso segue i file delle lezioni ordinati per data/ora nel nome, comprese le esercitazioni e le parti di una stessa giornata. Per ciascuna lezione il tutor riceve un outline dei passaggi, riferimenti paginati e collegamenti disponibili ai materiali. Deve leggere i passaggi e le slide originali necessari prima di salvare gli argomenti. Informazioni organizzative e programma citato dal docente vanno distinti dai concetti effettivamente spiegati.

Ogni argomento ha titolo, obiettivo, prerequisiti e fonti. Il backend richiede almeno una fonte della lezione scelta e rifiuta riferimenti a corsi diversi, temi riservati e soluzioni. Le attività devono citare fonti dell'argomento corrente. Il piano viene conservato: non è ricreato a ogni risposta. È una sintesi proposta dal modello, non un programma ufficiale certificato.

Quando manca la trascrizione finale ma sono disponibili OCR e allineamenti, la lezione rimane selezionabile con un avviso esplicito. Il tutor deve verificare i PDF associati e non attribuire al docente contenuti ricostruiti soltanto dall'OCR. Se esistono solo materiali, il percorso usa l'ordine naturale dei file, dichiarando che non è una cronologia verificata; esclude risultati, temi d'esame, soluzioni e file di sola organizzazione.

## Fasi di ciascun argomento

1. **Prerequisiti:** parole e concetti minimi con un esempio concreto, senza quiz su sigle non ancora spiegate.
2. **Spiegazione:** un concetto alla volta, definendo simboli, ipotesi e notazione del corso.
3. **Esempio svolto:** passaggi commentati e motivati.
4. **Prova guidata:** variante con aiuti progressivamente ridotti.
5. **Prova autonoma:** caso nuovo, senza anticipare suggerimenti e soluzione.
6. **Riepilogo:** cosa è stato affrontato e cosa rimane da chiarire.

Il pulsante **Prossimo passo** avanza quando lo studente lo desidera. La navigazione non certifica comprensione. Le attività e le correzioni generate restano provvisorie, anche quando il controllo meccanico di una risposta coincide con la chiave del modello.

Dopo un tentativo nella fase autonoma, proseguire aggiunge un richiamo proposto per il giorno successivo in **Ripassi**. È un promemoria separato dai richiami FSRS verificati. Aprire e terminare il richiamo ripristina il punto del percorso precedente; se si esce senza rispondere, il promemoria rimane disponibile. Non viene attribuita padronanza perché è trascorso un giorno.

## Persistenza e verifica

SQLite conserva sessione, lezione corrente, piano, argomento, fase, posizioni già visitate e richiami. Le attività mantengono i riferimenti a lezione/argomento/fase. I cambi di lezione e argomento conservano il cursore precedente; messaggi, bozze e tentativi usano il registro esistente.

Gli strumenti aggiunti sono `read_lesson`, `set_lesson_plan`, `advance_lesson_step`, `select_study_lesson`, `select_study_topic`. Cambi di direzione e avanzamenti dell'agente sono previsti soltanto su richiesta dello studente. Nella simulazione autonoma il percorso e questi strumenti non sono disponibili.

I test controllano ancoraggio alle fonti, ordine delle lezioni, conservazione dei collegamenti candidati, assenza di quiz iniziale, cambio di argomento, ripresa e richiami. Un test con il vero backend e SDK Pi usa un provider HTTP simulato per leggere fonti, salvare un piano e creare una spiegazione. I test browser verificano anche l'indisponibilità del provider senza perdita del percorso. La qualità didattica di una spiegazione commerciale va verificata con una sessione reale dello studente.
