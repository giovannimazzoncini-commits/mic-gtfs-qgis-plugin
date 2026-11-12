MIC_GTFS — INTERFACCIA PETROLIO / LIGHT — build tecnico 1.2.0

INSTALLAZIONE
Pacchetto completo, nessuna dipendenza pip. QGIS 3.28-3.x, non QGIS 4.
Disinstallare MIC_GTFS precedente (e disattivare GTFS semplice), riavviare QGIS,
Plugin > Gestisci e installa plugin > Installa da ZIP > scegliere MIC_GTFS.zip.
Reimportare GTFS originale. Dati salvati su disco non vengono cancellati.
Nome visibile MIC_GTFS; numero tecnico nei metadati per gli aggiornamenti.

NOVITA 1.2.0
- Layer fermate con nome descrittivo: "Fermate raggiungibili - 10 min - dalla 3125",
  "... - verso la 3125", "... - da e verso la 3125".
- Direzione "Entrambe": esegue Da qui e Verso qui e crea un layer unico con fermate
  uniche (unione, non somma). Campi da_min, verso_min (vuoto se non raggiungibile in
  quel verso) e ambito = da / verso / entrambi. Limite minuti applicato a ciascun
  verso separatamente; NON e un viaggio di andata e ritorno. Percorsi in due
  sottogruppi "Dalla ..." e "Verso la ..." anche nella scheda Collegamenti.
- Correzione errore "wrapped C/C++ object ... has been deleted": il plugin conserva
  gli ID dei layer, ignora layer di dettaglio gia rimossi e si azzera alla chiusura
  del progetto; se il layer fermate e stato rimosso chiede di reimportare il feed.

INTERFACCIA NUOVA
Stile chiaro con accento petrolio, sezioni su card, titolo e testi differenziati.
Pannello dock a destra/sinistra o sganciabile, pulsante toolbar mostra/nasconde.
Schede Analisi e Collegamenti. Feed e fermata selezionata visibili.
Raggiungibilita con selettore Da qui/Verso qui/Entrambe, preset 10/15/20 minuti e Altro,
nessun cambio/massimo un cambio. Parametri avanzati richiudibili. Date esplicite.
Modalita alternative: percorsi completi/varianti, passaggi giornalieri.
Colori light espliciti limitati al corpo del plugin: non cambia tema globale QGIS.
Non e implementato tema scuro adattivo. QSS e font possono variare fra OS.
Collegamenti: ricerca, card con badge colorati e sottotitolo fermata cambio,
prima linea > combinazione + stop_id > destinazioni. I badge sono compatti,
i dettagli lunghi in tooltip. Doppio clic su destinazione per itinerario.
Riepilogo selezione sotto albero. Mostra solo questo itinerario nasconde ultimo
gruppo rete MIC_GTFS, non altri layer utente (spegnere fermate feed se necessario).
Ripristina elimina solo dettaglio temporaneo e riaccende rete. Dettagli salvati
sono esclusi dalla pulizia e rimangono disponibili. Non invia dati a servizi web.

SALVATAGGIO
Temporaneo default. Salva su file dopo calcolo apre dialogo export; oppure scheda
Collegamenti > Salva risultati per analisi, collegamento o itinerario visualizzato.
Formato scelto in dialogo: GeoPackage o Shapefile. GPKG richiede NUOVO file, non
sovrascrive file esistenti. Shapefile crea sottocartella univoca, un layer per file.
Tabelle senza geometria esportate DBF. Tutti i campi generati hanno <=10 caratteri.
UTF-8. Tenere insieme .shp .shx .dbf .prj .cpg, non soltanto .shp.
Tutti i file controllati riaprendoli prima di ricollegare layer a disco. Il progetto
usa poi i dati persistenti. Salvataggio non atomico: errore/annullamento puo lasciare
file parziali. Originali non ricollegati finche scrittura completa non riesce.
QLR aggiuntivo per gruppi/stili; QML per Shapefile; manifest JSON con parametri
calcolo memorizzati all'elaborazione, non riletti da controlli eventualmente cambiati.
Stili GPKG in QLR, non layer_styles. Salvare anche progetto QGIS. Caricare QLR per
ripristinare gerarchia; singole tabelle GPKG non ripristinano gruppi da sole.
Feed importato non persistente e non incluso nel salvataggio analisi.

MOTORE MANTENUTO
Una fermata origine/destinazione, un cambio stessa stop_id, niente cammino.
Cambio inutile eliminato se diretto compatibile parte non prima e arriva non dopo;
soglia >1 minuto vantaggio predefinita modificabile. Frontiera per partenza/arrivo/
cambi, una soluzione rappresentativa a parita completa. Rete unione opportunita
su orari diversi, NON viaggio simultaneo; gruppo per sequenza linee e fermata cambio.
Elenco: minimo per destinazione + sequenza + interscambio dopo filtro, non tutte le
corse/varianti/orari. Budget totale include attesa cambio, esclude attesa iniziale.
Lun-ven settimana scelta incluse festivita/zeri e eccezioni, non feriale annuo.
Orari >24:00. Frequencies non vuoto blocca analisi orarie; transfers non vuoto
blocca cambi. Solo pickup/dropoff 0 o vuoto: altri esclusi conservativamente.
Orari mancanti saltati, nessuna interpolazione. Non GTFS flex o realtime.
Shape_dist_traveled quando compatibile, altrimenti DP monotona lungo shape intero
per sequenza fermate, tolleranza 150 m circa, proiezione locale approssimata.
Anelli e ripassi da verificare visualmente; nessuna garanzia aggancio univoco.
Segmenti senza geometria omessi e segnalati, niente rette di ripiego.
Non routing stradale indipendente, non poligoni isocroni, non fronte a meta fermate.
Percorsi completi separati da raggiungibilita, varianti route/direction/shape/
sequenza pickup-dropoff, periodo opzionale; shape assenti omessi.
Passaggi conta righe stop_times, non veicoli fisici, media dei giorni considerati.

STATO TECNICO
Sintassi Python, ZIP, e 6 asserzioni sintetiche motore controllati. Interfaccia,
Qt, writer GPKG/SHP e docking NON provati in runtime QGIS. Nessun test completo GTT.
CSV in RAM, ricerca esaustiva lenta con feed grandi, molti layer per collegamenti.
Thread principale con annullamento periodico, non task background. Non chiudere
progetto o disinstallare plugin durante calcolo. Provare prima una singola data
con pochi risultati e verificare esportazione e riapertura su una piccola analisi.
