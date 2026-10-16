# Polimi Lectures

Archivio locale incrementale di registrazioni Polimi/Webex, predisposto per più corsi.
Python 3.9+, Playwright, HTTPX e FFmpeg. Non richiede aria2, password in configurazione o servizi cloud.

## Avvio su macOS

1. Apri `Setup.command`: prima chiede email Webex/Polimi e cartella dati, anche su un disco esterno. Invio mantiene i valori esistenti. Installa poi le dipendenze nella cartella del programma.
2. Apri `Avvia.command`: parte direttamente il percorso guidato, senza scegliere prima un’operazione.
3. Scrivi il nome o il codice del corso, oppure premi Invio per l’ultimo corso usato, incluso il suo anno accademico. Sono tollerati piccoli errori, ad esempio `paralel computing`. Digita `m` per le altre opzioni o `q` per uscire.
4. Completa il login Polimi/SPID nel browser. L'app apre direttamente WeBeep, attende l'accesso e cerca il corso.
5. Se ci sono più corrispondenze o anni accademici, scegli il corso dall'elenco nel Terminale.
6. L'app apre l'archivio registrazioni e raccoglie l'elenco completo usando «tutte» o passando alle pagine successive.
7. Scegli **1** per una lezione di prova, **2** per un intervallo di date, **3** per tutte oppure **4** per i materiali del corso.
8. Per le date accetta `gg/mm/aaaa` e `YYYY-MM-DD`. Gli estremi sono inclusi; Invio lascia un estremo aperto. Vengono aperte su Webex solo le lezioni selezionate.

L'email Webex configurata viene inserita automaticamente; password, MFA ed eventuale
password della registrazione rimangono manuali. L’app tenta anche l’avvio automatico del player; intervieni solo se il servizio richiede password/MFA o segnala un errore.
Il catalogo del percorso guidato usa il nome completo del corso, incluso l'anno accademico,
per evitare di mescolare corsi omonimi. I video già presenti vengono verificati e saltati.

Il percorso è basato sugli HTML reali salvati dall'utente e su test browser con pagine
simulate; la navigazione completa autenticata deve essere provata sul portale corrente.
Se un corso usa una struttura diversa, resta disponibile l'opzione **6 — Raccolta manuale** in `Gestisci.command` (oppure digita `m` all’avvio):
raggiungi l'elenco, usa `s` per i link o `a` per i pulsanti di riproduzione, cambia pagina
se necessario e termina con `q`. Gli HTML diagnostici vengono conservati anche nel percorso guidato.

Se FFmpeg manca, installalo con il tuo gestore di pacchetti (ad esempio `brew install ffmpeg`).
Non è installato automaticamente da questo progetto. Se Finder non apre i launcher,
eseguili da Terminale con `bash Setup.command` e `bash Avvia.command`.

## Terminale

Esegui dalla cartella del progetto; non serve attivare l'ambiente virtuale:

```bash
.venv/bin/python -m polimi_lectures.cli doctor
.venv/bin/python -m polimi_lectures.cli login
.venv/bin/python -m polimi_lectures.cli wizard --course "Parallel Computing"
.venv/bin/python -m polimi_lectures.cli discover --course "Parallel Computing"
.venv/bin/python -m polimi_lectures.cli download --course "Parallel Computing" --limit 1
.venv/bin/python -m polimi_lectures.cli download --course "Parallel Computing"
.venv/bin/python -m polimi_lectures.cli status
```

Puoi partire da una pagina corrente con `discover --url 'URL'` (meglio usare la modalità
guidata se l'URL contiene token). Se serve, passa `--lesson-selector 'CSS'` a `discover`:
il comando `a` cliccherà solo i controlli indicati, sulla pagina principale.
Le iframe vengono esaminate per i link, ma i loro pulsanti richiedono navigazione manuale.

Importazione di link Webex (un URL HTTPS per riga):

```bash
.venv/bin/python -m polimi_lectures.cli add --course "Parallel Computing" --file lezioni.txt
.venv/bin/python -m polimi_lectures.cli add --course "Parallel Computing" --url 'URL_WEBEX' --title 'Lezione 1' --date 2026-10-14
```

`add` sullo stesso ID aggiorna titolo/data/link senza duplicare il video.
Usa `download --before YYYY-MM-DD` per un limite di data **inclusivo**:
le registrazioni senza data sono escluse e conteggiate nel messaggio iniziale.
Non viene impostata una data d'esame presunta.

`--root /percorso` e `--channel chrome` sono opzioni globali, prima del comando. Senza `--root`, tutti i comandi usano la cartella dati scelta nel setup.
Normalmente il browser usato è il Chromium dedicato installato dal setup.

## Download e archivio

Nella cartella del programma rimangono `.venv`, `.state/settings.json`,
`.state/browser` (sessione Polimi/Webex) e `.state/browsers` (Chromium).
Nella cartella dati selezionata vengono salvati:

```text
.state/
  catalog.sqlite3     # catalogo e link d'accesso, privato
  debug-html/         # catture diagnostiche delle pagine
corsi/
  Parallel-Computing/
    DATA_TITOLO_ID/
      video.mp4
      metadata.json
```

I nomi includono l'ID completo della registrazione. La data è presente solo quando rilevata
o fornita. Il percorso resta stabile anche se in seguito arriva un titolo migliore.
Il download cerca MP4 diretti nelle risposte del player Webex; in alternativa legge le
playlist osservate nel browser. Per playlist byte-range con un unico MP4 risolve quel file,
come nel procedimento manuale. Per le altre usa FFmpeg, copiando i flussi senza ricodifica.

Gli MP4 HTTP interrotti possono essere ripresi se il server offre ETag/Last-Modified e Range;
altrimenti ripartono da zero. HLS riparte da zero. Un file viene segnato completo solo dopo
aver verificato durata positiva e presenza di audio e video con ffprobe: è un controllo
strutturale, non una decodifica integrale di ogni fotogramma. I file già presenti vengono
verificati e saltati. Gli errori di una lezione non fermano le successive.

Per nuove lezioni, ripeti raccolta e download: SQLite deduplica per corso e ID Webex.
Puoi usare nomi di corso differenti per ampliare l'archivio. Audio e trascrizioni potranno
essere aggiunti nelle stesse cartelle in una fase successiva.

## Dati locali

Non inserire cookie o password in chat. Il login avviene nel browser dedicato e lo stato
privato è in `.state`, con permessi restrittivi ed esclusione da Git. `.venv` e video sono
esclusi da Git. Le URL firmate dei media e le risposte complete dell'API non vengono
salvate; il database conserva il collegamento Webex necessario a riaprire la registrazione,
che può contenere parametri di accesso. Nei metadata esportabili le query sono rimosse
(tranne RCID identificativo). Non condividere `.state` o file di link con token.
FFmpeg riceve temporaneamente URL e cookie come argomenti del processo locale.

## Verifica sviluppo

```bash
.venv/bin/python -m unittest discover -s tests -v
```

I test usano un server HTTP locale e video sintetici, non credenziali Polimi.
Il test sul portale autenticato richiede una prima prova nel browser dell'utente.

## Riferimenti consultati

- https://github.com/paolobasso99/polimi_recordings_downloader (archiviato; issue RecMan)
- https://github.com/jacopo-j/WebXDownloader (campi stream/fallbackPlaySrc)
- https://github.com/beryxz/unifi-webex-dl (playlist byte-range e MP4)
- https://playwright.dev/python/docs/auth
- https://playwright.dev/python/docs/network

Implementazione originale; non copia il codice dei progetti elencati.

## Email Webex e HTML diagnostici

La configurazione locale `.state/settings.json`, nella cartella del programma, contiene email Polimi, `data_dir` e `debug_html`.
Quando compare il modulo email su un dominio Webex, il programma inserisce l'indirizzo
configurato e preme Accedi/Avanti una sola volta per documento. Password e MFA rimangono
manuali; l'assistente non compila moduli su domini esterni a Webex.

Con `debug_html: true` vengono raccolte copie del DOM delle pagine e iframe in
`.state/debug-html/SESSIONE/`: dopo le navigazioni, periodicamente quando cambia il DOM,
e prima della chiusura. I redirect molto rapidi possono non produrre una copia leggibile.
Sono snapshot HTML, non archivi offline completi: CSS, immagini, shadow DOM e canvas
non vengono esportati. I valori dei campi password e hidden vengono rimossi dalla copia,
senza modificare la pagina reale. Gli HTML possono comunque contenere URL o dati privati
nei link e negli script: restano nella cartella privata esclusa da Git, con permessi 600.
Nelle catture HTML non vengono esportati cookie o risposte di rete. I metadata delle catture omettono query e
frammenti degli URL. Ogni sessione ha una cartella distinta; contenuti identici non vengono
risalvati. Per disattivare la diagnostica imposta `debug_html` a `false`.

Le modifiche diventano attive alla successiva apertura di `Avvia.command`; non si
applicano a un processo già in esecuzione. Gli HTML di tentativi precedenti all'attivazione
non sono disponibili retroattivamente.

## Cambiare email o disco dati

Chiudi il browser del downloader e termina la prova in corso prima di cambiare cartella.
Riapri `Setup.command`: chiede prima l'email, poi la cartella dati. Puoi scrivere ad esempio
`/Volumes/Nome Disco/Lezioni Polimi` oppure trascinare una cartella dal Finder nel Terminale.
I percorsi con spazi sono supportati. Il disco esterno deve essere collegato e montato.
Per conservare un valore attuale, premi Invio. I launcher mostrano la cartella dati in uso.

Se esistono dati nella vecchia posizione, il setup copia catalogo, HTML diagnostici e
cartella `corsi` nella destinazione, verificando il contenuto del catalogo SQLite prima
di aggiornare la configurazione. La destinazione non deve già contenere `.state` o
`corsi`, per evitare sovrascritture. Gli originali vengono conservati; potranno essere
rimossi manualmente dopo aver verificato il nuovo archivio. Non vengono copiati ambiente
Python, browser, sessione di accesso o cache del programma. La sessione resta locale e
viene riutilizzata fino alla sua scadenza.

Il programma si ferma se la cartella dati configurata non è disponibile, invece di
creare un archivio vuoto al posto di un disco scollegato. I dati della cartella esterna
sono privati come quelli locali: non pubblicare catalogo o HTML diagnostici.

Per modificare soltanto la configurazione, senza eseguire l'installazione delle dipendenze:

```bash
.venv/bin/python -m polimi_lectures.configure
```

## Riutilizzo del login

Oltre al profilo Chromium, l'app salva cookie e localStorage Polimi/Webex nel file privato
`.state/auth-state.json` accanto al programma. Il salvataggio avviene periodicamente e
prima della chiusura; all'avvio vengono ripristinati i cookie mancanti e i valori di
localStorage assenti. Le scadenze originali non vengono modificate e un cookie più recente
presente nel profilo non viene sovrascritto. Il file è escluso da Git e ha permessi 600;
contiene dati di accesso e non deve essere condiviso. Lo stato di PosteID non viene
esportato in questo file. Il file resta locale anche cambiando disco dati.

Il percorso guidato verifica prima l'accesso a WeBeep e prosegue direttamente quando è
già disponibile. Se Polimi/Webex hanno invalidato la sessione, sarà richiesto un nuovo
login: il salvataggio locale non può mantenere valida una sessione scaduta sul server.
Dopo l'aggiornamento potrebbe servire un primo accesso per creare lo stato esplicito.

Il salvataggio periodico dell'accesso legge i cookie e il localStorage dai frame già
aperti. Non usa `storage_state()` durante l'esecuzione, perché Playwright può creare
schede temporanee per leggere origin non più aperti e riportare Chrome in primo piano.
Per origin non aperti conserva i valori salvati in precedenza. Le catture HTML restano attive.
Il login email supporta anche il markup Webex con `button#IDButton2` dichiarato `role="link"`:
compila il campo, attiva la validazione e invia Accedi. I tentativi con pulsante disabilitato
non spostano il focus nel campo email. Le password e le conferme SPID/MFA richieste dal
servizio restano nel browser dell'utente.

## Avvio semplificato

`Avvia.command` propone direttamente il corso. La scelta dell'ultimo corso viene salvata
in `last_course` nella configurazione locale; premendo Invio la ricerca usa il nome completo,
anno compreso, evitando di richiedere di nuovo la scelta tra anni accademici. Per cambiarlo
basta scrivere un nuovo nome. Il passaggio automatico SSO verso RecMan viene atteso senza
conferme nel Terminale. Solo una richiesta effettiva di autenticazione richiede intervento.

Nel percorso normale sono mostrati titoli brevi, percentuale e tempo residuo stimato,
poi il conteggio di file scaricati, già presenti e non riusciti, con il percorso di salvataggio.
Il titolo completo rimane nei metadati. Dopo il riepilogo appare un menu per continuare: altre lezioni, materiali, eliminazione del
video di prova, cartella nel Finder o cambio corso. `q` termina la sessione. I dettagli tecnici sono nascosti ma la diagnostica HTML resta attiva.
Le funzioni precedenti sono in `Gestisci.command`, accessibile digitando `m` all'avvio.
I comandi CLI diretti mantengono l'output dettagliato.

## Continuare dopo una prova

Dopo il download il browser resta aperto e il menu chiede cosa fare: **1** altre lezioni,
**2** materiali, **3** eliminare il video di prova (solo quando una prova è stata scelta),
**4** aprire l'archivio, **5** cambiare corso, **q** uscire. Il corso e l'elenco delle lezioni
restano disponibili nella stessa sessione. Eliminare la prova rimuove solo `video.mp4`
e i suoi `metadata.json`, rimettendo la registrazione in attesa nel catalogo. Appunti,
trascrizioni e altri file non vengono toccati. La scelta 3 è l'azione di eliminazione.

La prima ricerca di un corso chiede di scegliere l’anno quando ci sono più risultati.
La scelta viene ricordata separatamente per ciascun corso: scrivendo di nuovo il nome
breve viene riutilizzato il corso/anno scelto, anche dopo aver aperto altri corsi,
se è ancora disponibile. Il meccanismo vale per qualunque nome di corso. Per cambiare anno scrivilo nel nome,
ad esempio `parallel computing 2026-27`. Le preferenze sono nel file locale settings.json.

## Materiali WeBeep

Dal menu delle registrazioni scegli **4**, oppure dopo un download scegli **2**.
Puoi accedere direttamente anche con **m → 7** all'avvio, senza passare da RecMan,
o dal Terminale con:

```bash
.venv/bin/python -m polimi_lectures.cli materials --course "Parallel Computing"
```

La funzione esplora cartelle, risorse e pagine del corso; propone tutti i materiali
individuati, singoli elementi (es. `1,3,5-8`) oppure interi gruppi/cartelle. Le sottocartelle
dei file vengono mantenute. Le pagine come Links sono salvate come HTML senza script,
form o iframe; i collegamenti esterni rimangono link, non vengono scaricati ricorsivamente.
I file sono in `corsi/NOME-CORSO/materiali/`, con un indice per verificare i file già
scaricati e usare richieste condizionali quando il server fornisce ETag/Last-Modified.
Le cartelle senza file leggibili vengono segnalate esplicitamente e i loro HTML salvati.

Verificato sugli HTML reali delle cartelle Exams e Course lectures: 63 file riconosciuti.
Eseguita anche una prova autenticata di download di un PDF in una cartella temporanea,
rimossa al termine. Per altri corsi il funzionamento dipende dai tipi di risorsa usati;
moduli che restituiscono una pagina invece di un file sono segnalati, senza salvarli
come PDF erroneamente. I materiali non vengono scaricati automaticamente senza selezione.

## Avanzamento globale delle lezioni

Durante il download sono mostrate due righe: avanzamento della lezione corrente e
avanzamento di tutte le lezioni selezionate, con MB, percentuale e conteggio delle lezioni
verificate. Il simbolo ≈ indica che il totale include dimensioni arrotondate del portale;
le dimensioni esatte vengono aggiornate dalle risposte HTTP e dai video completati.
Se manca una dimensione, il totale è indicato come da determinare. I file già presenti
contano dopo la verifica; i byte di una ripresa vengono conteggiati una sola volta.
Il totale riguarda la selezione corrente, non tutti i corsi dell’archivio.

## Trascrizione locale con Whisper

All’avvio scegli il corso, poi **2) Trascrivi le lezioni scaricate**. Non serve
accedere a WeBeep: il corso è scelto dal catalogo locale e mantiene la preferenza
dell’anno. Puoi trascrivere tutte le lezioni da completare, la prima per una prova
o una selezione numerica. Dopo un download la stessa funzione è nel menu **6**;
nel menu avanzato è **8**, mentre **9** configura il modello.

Il primo utilizzo permette di scaricare un modello oppure indicare un file modello
già presente (anche trascinandolo dal Finder). Il motore è
[whisper.cpp](https://github.com/ggml-org/whisper.cpp), con modelli **GGML .bin**:
i checkpoint .pt di openai-whisper e le cartelle CTranslate2 richiedono un altro
motore e non sono accettati da questa integrazione. Il menu usa il catalogo del
repository indicato dal progetto, mostra le dimensioni e verifica SHA-256 dopo il
download. I modelli .en sono solo inglese; q5/q8 indicano versioni più compatte.
La scelta rimane salvata, e può essere cambiata dal menu del modello. Il programma
propone small per iniziare; la lingua può essere auto, en, it o un altro codice
Whisper. Non viene richiesta la traduzione in inglese.

Su Apple Silicon viene preferito /opt/homebrew/bin/whisper-cli quando disponibile.
Se manca, installa il motore con [brew install whisper.cpp](https://formulae.brew.sh/formula/whisper.cpp).
FFmpeg e ffprobe sono quelli già usati per i video. Non servono nuove dipendenze Python
pesanti. L’audio è elaborato localmente.

Ogni lezione ha una cartella trascrizione accanto a video.mp4, contenente:
- trascrizione.txt: testo leggibile;
- trascrizione.srt: sottotitoli con tempi riferiti all’intera lezione;
- trascrizione.json: segmenti, tempi e informazioni di provenienza;
- sessioni/: blocchi di lavoro e checkpoint;
- completa.json: verifica di completamento e integrità delle esportazioni.

Il lavoro viene salvato dopo ogni blocco di **5 minuti**. In caso di chiusura, crash
o Ctrl+C, scegli nuovamente la trascrizione del corso: i blocchi completi vengono
riutilizzati e solo il blocco interrotto viene rielaborato. La ripresa non avviene
a metà di un blocco. Anche un crash dopo l’ultimo blocco, prima delle esportazioni,
permette di ricostruire i file senza rifare Whisper. I blocchi danneggiati vengono
rifatti. Le trascrizioni complete sono saltate dopo aver verificato la presenza e
gli hash degli output e che il video non sia cambiato. Sono saltate anche quando
si sceglie un modello diverso. Per le trascrizioni parziali, cambiare modello,
lingua o durata dei blocchi crea una sessione separata e conserva quella precedente;
riselezionando le stesse impostazioni la si può riprendere. I tagli tra blocchi
possono ridurre il contesto del riconoscimento: il testo precedente viene passato
come contesto al blocco successivo, ma la trascrizione richiede comunque revisione.

Modelli, audio temporaneo e checkpoint stanno nella **cartella dati** scelta nel
setup. I modelli scaricati sono in modelli/whisper; le preferenze Whisper in
.state/whisper/settings.json. Un download interrotto del modello conserva il parziale
e tenta la ripresa HTTP; se il server non la supporta ricomincia quel file. Il modello
viene utilizzato solo dopo la verifica completa. Un modello indicato con percorso
esterno viene letto nella posizione scelta. Il cambio cartella dati copia anche i
modelli interni e aggiorna il loro percorso.

Comandi diretti:

```bash
.venv/bin/python -m polimi_lectures.cli transcribe --course "Nome del corso"
.venv/bin/python -m polimi_lectures.cli transcribe --course "Nome del corso" --all --model "/disco/ggml-small.bin" --language en
.venv/bin/python -m polimi_lectures.cli transcribe --course "Nome del corso" --model-name small --limit 1 --language auto
.venv/bin/python -m polimi_lectures.cli whisper-model
```

--engine consente di specificare whisper-cli; --chunk-seconds cambia la durata dei
blocchi (predefinita 300). Non cancellare sessioni/ se vuoi mantenere la ripresa.
