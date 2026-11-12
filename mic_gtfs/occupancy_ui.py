"""Scheduled conflicts panel for MIC_GTFS. No realtime placeholder calculation."""
import copy,datetime as dt,uuid,json,csv,os
from pathlib import Path
from qgis.PyQt.QtCore import QDate,QTime,Qt
from qgis.PyQt.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,QLabel,QPushButton,QDateEdit,QTimeEdit,QSpinBox,QCheckBox,QTabWidget,QTableWidget,QTableWidgetItem,QMessageBox,QFileDialog,QHeaderView
from qgis.core import QgsApplication,QgsProject,QgsVectorFileWriter
from .occupancy_controller import OccupancyTask
from .occupancy_results import TABLES,build_layers,display_value

LABELS={'area_id':'Area','passages':'Passaggi','capacity':'Stalli','peak':'Picco simultaneo','start':'Inizio','end':'Fine','overlap_seconds':'Sovrapposizione (s)','exceed_seconds':'Superamento (s)','max_excess':'Eccedenza massima','excess_stall_seconds':'Stalli-secondo eccedenti','episodes':'Episodi','event_id':'ID visita','event_ids':'Visite coinvolte','trip_id':'Corsa','route_id':'ID linea','line':'Linea','stop_id':'Fermata','stop_sequence':'Sequenza','arrival':'Arrivo','departure':'Partenza','source':'Sorgente','occupancy_basis':'Modello occupazione','seconds':'Durata (s)','concurrent':'Contemporanei','excess':'Eccedenza','reason':'Segnalazione','excluded_reported':'Esclusioni segnalate','status':'Stato'}

class ConflictsPanel(QWidget):
    def __init__(self,plugin):
        super().__init__();self.plugin=plugin;self.token=0;self.task=None;self.stop_ids=[];self.result=None;self.stops_snapshot={};self.disposed=False;self.dirty=False
        v=QVBoxLayout(self);v.addWidget(QLabel('CONFLITTI FERMATA — programmato sperimentale'))
        self.info=QLabel('Importa il feed, seleziona fermate e acquisisci la selezione. Non serve calcolare la raggiungibilita.');self.info.setWordWrap(True);v.addWidget(self.info)
        form=QFormLayout();v.addLayout(form)
        self.mode=QComboBox();self.mode.addItems(['Programmato','Real-time — non disponibile','Storico — non disponibile'])
        self.mode.model().item(1).setEnabled(False);self.mode.model().item(2).setEnabled(False);form.addRow('Sorgente',self.mode)
        self.date=QDateEdit(QDate.currentDate());self.date.setCalendarPopup(True);form.addRow('Data civile analizzata',self.date)
        self.begin=QTimeEdit(QTime(0,0));self.end=QTimeEdit(QTime(0,0));self.begin.setDisplayFormat('HH:mm');self.end.setDisplayFormat('HH:mm');form.addRow('Dalle',self.begin);form.addRow('Alle',self.end)
        hint=QLabel('Fine <= inizio: giorno successivo. 00:00–00:00 = giornata intera.');hint.setWordWrap(True);v.addWidget(hint)
        self.timezone=QComboBox();self.timezone.setEditable(True);self.timezone.setEditText('');self.timezone.setToolTip('Fuso del GTFS (agency_timezone), es. Europe/Rome. Se assente va specificato esplicitamente.');form.addRow('Fuso orario GTFS',self.timezone)
        self.group=QCheckBox('Le fermate selezionate condividono gli stessi stalli');form.addRow(self.group)
        self.capacity=self.spin(form,'Stalli (0 = non noto)',0,100,0)
        self.dwell=self.spin(form,'Sosta assunta (s)',1,3600,45)
        self.clearance=self.spin(form,'Liberazione aggiuntiva (s)',0,600,10)
        self.use_dep=QCheckBox('Usa arrivo–partenza se intervallo positivo');self.use_dep.setChecked(True);form.addRow(self.use_dep)
        self.bin=QComboBox();self.bin.addItems(['15','30','60']);self.bin.setCurrentText('60');form.addRow('Fasce (min, dall’inizio analisi)',self.bin)
        warning=QLabel('45 s e 10 s sono valori iniziali illustrativi, non standard progettuali. Modello con stalli indipendenti: non simula code/manovre. Conta visite GTFS; non riconcilia automaticamente cambi corsa dello stesso veicolo.');warning.setWordWrap(True);v.addWidget(warning)
        actions=QHBoxLayout();v.addLayout(actions)
        self.pick=QPushButton('Usa fermate selezionate');actions.addWidget(self.pick);self.pick.clicked.connect(self.capture)
        self.run=QPushButton('Calcola conflitti');actions.addWidget(self.run);self.run.clicked.connect(self.start)
        self.cancel=QPushButton('Annulla');self.cancel.setEnabled(False);actions.addWidget(self.cancel);self.cancel.clicked.connect(self.cancel_task)
        self.tabs=QTabWidget();v.addWidget(self.tabs,1);self.tables={}
        for key,label in TABLES:
            table=QTableWidget();table.setEditTriggers(QTableWidget.NoEditTriggers);table.setSelectionBehavior(QTableWidget.SelectRows);self.tables[key]=table;self.tabs.addTab(table,label)
        bottom=QHBoxLayout();v.addLayout(bottom)
        for text,fn in [('Mostra sulla mappa',self.show_map),('Esporta GeoPackage',self.export_gpkg),('Esporta CSV',self.export_csv)]:
            button=QPushButton(text);bottom.addWidget(button);button.clicked.connect(lambda checked=False,f=fn:self.guarded(f))
        for w,signal in [(self.date,'dateChanged'),(self.begin,'timeChanged'),(self.end,'timeChanged'),(self.timezone,'currentTextChanged'),(self.capacity,'valueChanged'),(self.dwell,'valueChanged'),(self.clearance,'valueChanged'),(self.bin,'currentTextChanged'),(self.group,'toggled'),(self.use_dep,'toggled')]:getattr(w,signal).connect(self.changed)
    def spin(self,form,label,lo,hi,value):
        w=QSpinBox();w.setRange(lo,hi);w.setValue(value);form.addRow(label,w);return w
    def guarded(self,fn):
        try:fn()
        except Exception as error:QMessageBox.warning(self,'MIC_GTFS — Conflitti',str(error))
    def changed(self,*args):
        self.dirty=True
        if self.task is not None:self.token+=1;self.task.cancel();self.task=None;self.run.setEnabled(True);self.cancel.setEnabled(False)
        if self.result is not None:self.info.setText('Parametri modificati: risultati precedenti da ricalcolare. Restano riferiti alla configurazione originaria.')
    def cancel_task(self):
        self.token+=1
        if self.task is not None:self.task.cancel();self.task=None
        self.run.setEnabled(True);self.cancel.setEnabled(False);self.info.setText('Calcolo annullato; nessun risultato parziale pubblicato.')
    def dispose(self):
        self.disposed=True;self.cancel_task()
    def invalidate_feed(self):
        self.cancel_task();self.stop_ids=[];self.result=None;self.stops_snapshot={}
        for table in self.tables.values():table.clear();table.setRowCount(0);table.setColumnCount(0)
        self.info.setText('Feed/progetto cambiato: acquisisci nuovamente le fermate.')
    def capture(self):self.guarded(self._capture)
    def _capture(self):
        if self.plugin.busy:raise ValueError('Attendi il termine dell’importazione o analisi in corso.')
        layer=self.plugin.stoplayer()
        if layer is None:raise ValueError('Importa il feed: manca il layer fermate.')
        ids=sorted({str(f['stop_id']) for f in layer.selectedFeatures()})
        if not ids:raise ValueError('Seleziona almeno una fermata nel layer MIC_GTFS del feed.')
        self.stop_ids=ids;self.changed()
        zones={r.get('agency_timezone','').strip() for r in self.plugin.data.get('agency',[]) if r.get('agency_timezone')}
        if len(zones)==1 and not self.timezone.currentText():self.timezone.setEditText(zones.pop())
        self.info.setText('Fermate acquisite: '+', '.join(ids)+'. Verifica fuso, stalli e durate; poi calcola.')
    def start(self):self.guarded(self._start)
    def _start(self):
        if self.plugin.busy:raise ValueError('Attendi il termine dell’altra operazione MIC_GTFS.')
        if self.task is not None:raise ValueError('Calcolo gia in corso.')
        if not self.stop_ids:raise ValueError('Acquisisci prima le fermate selezionate.')
        if not self.timezone.currentText().strip():raise ValueError('Specifica il fuso GTFS o reimporta il feed per leggere agency.txt.')
        selected=set(self.stop_ids);rows=[dict(r) for seq in self.plugin.seq.values() for r in seq if r.get('stop_id') in selected];tids={r['trip_id'] for r in rows}
        data={'rows':rows,'trips':{t:dict(self.plugin.trips[t]) for t in tids},'routes':copy.deepcopy(self.plugin.routes),'calendar':copy.deepcopy(self.plugin.data.get('calendar',[])),'calendar_dates':copy.deepcopy(self.plugin.data.get('calendar_dates',[])),'frequencies':copy.deepcopy(self.plugin.data.get('frequencies',[]))}
        if not data['calendar'] and not data['calendar_dates']:raise ValueError('Calendario di servizio assente: impossibile identificare le corse attive.')
        if not rows:raise ValueError('Nessun evento stop_times per le fermate acquisite.')
        area='AREA:'+','.join(self.stop_ids)
        cfg={'analysis_id':uuid.uuid4().hex,'mode':'scheduled','date':self.date.date().toString('yyyy-MM-dd'),'from':self.begin.time().toString('HH:mm'),'to':self.end.time().toString('HH:mm'),'timezone':self.timezone.currentText().strip(),'stop_areas':{sid:area if self.group.isChecked() else sid for sid in self.stop_ids},'capacity':self.capacity.value() or None,'dwell':self.dwell.value(),'clearance':self.clearance.value(),'use_departure':self.use_dep.isChecked(),'bin_minutes':int(self.bin.currentText()),'feed_name':os.path.basename(getattr(self.plugin,'feedpath','')),'capacity_model':'independent_berths','event_count':'GTFS stop visits, not reconciled physical vehicles'}
        self.pending_stops={sid:dict(self.plugin.stops[sid]) for sid in self.stop_ids};self.token+=1;self.dirty=False;self.task=OccupancyTask(self,self.token,data,cfg);self.run.setEnabled(False);self.cancel.setEnabled(True);self.info.setText('Elaborazione in background…');QgsApplication.taskManager().addTask(self.task)
    def task_finished(self,token,success,result,failure,cancelled):
        if self.disposed or token!=self.token:return
        self.task=None;self.run.setEnabled(True);self.cancel.setEnabled(False)
        if not success:
            self.info.setText('Annullato' if cancelled else 'Errore: '+str(failure));return
        self.result=result;self.stops_snapshot=self.pending_stops;self.render()
        self.info.setText('Completato: '+str(len(result['events']))+' visite, '+str(len(result['episodes']))+' episodi di superamento; '+str(len(result['diagnostics']))+' segnalazioni. Modello programmato, non code osservate.')
    def render(self):
        timezone=self.result['config']['timezone']
        for key,table in self.tables.items():
            rows=self.result[key];columns=list(dict.fromkeys(k for row in rows for k in row));table.clear();table.setColumnCount(len(columns));table.setHorizontalHeaderLabels([LABELS.get(c,c) for c in columns]);table.setRowCount(min(len(rows),20000))
            for i,row in enumerate(rows[:20000]):
                for j,col in enumerate(columns):table.setItem(i,j,QTableWidgetItem(display_value(col,row.get(col),timezone)))
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            table.setToolTip('Vista limitata a 20.000 righe; esportazione completa.')
    def require_result(self):
        if self.result is None:raise ValueError('Calcola prima i conflitti.')
        if self.dirty:raise ValueError('Parametri cambiati: ricalcola prima di esportare o mostrare i risultati.')
    def show_map(self):
        self.require_result();layers=build_layers(self.result,self.stops_snapshot);root=QgsProject.instance().layerTreeRoot();cfg=self.result['config'];group=root.addGroup('MIC_GTFS — Conflitti programmati — '+cfg['date']+' — '+cfg['analysis_id'][:6])
        for kind,layer in layers:QgsProject.instance().addMapLayer(layer,False);group.addLayer(layer)
    def export_gpkg(self):
        self.require_result();path,_=QFileDialog.getSaveFileName(self,'Nuovo GeoPackage conflitti','','GeoPackage (*.gpkg)')
        if not path:return
        if not path.lower().endswith('.gpkg'):path+='.gpkg'
        if os.path.exists(path):raise ValueError('Scegli un file nuovo: nessuna sovrascrittura.')
        layers=build_layers(self.result,self.stops_snapshot)
        for i,(kind,layer) in enumerate(layers):
            opts=QgsVectorFileWriter.SaveVectorOptions();opts.driverName='GPKG';opts.fileEncoding='UTF-8';opts.layerName=kind;opts.actionOnExistingFile=QgsVectorFileWriter.CreateOrOverwriteFile if i==0 else QgsVectorFileWriter.CreateOrOverwriteLayer
            outcome=QgsVectorFileWriter.writeAsVectorFormatV3(layer,path,QgsProject.instance().transformContext(),opts)
            if outcome[0]!=QgsVectorFileWriter.NoError:raise ValueError('Export fallito; file parziale possibile: '+str(outcome))
        Path(path+'.analysis.json').write_text(json.dumps(self.result['config'],ensure_ascii=False,indent=2),encoding='utf-8');self.info.setText('GeoPackage e configurazione salvati. Non contiene uno storico real-time.')
    def export_csv(self):
        self.require_result();parent=QFileDialog.getExistingDirectory(self,'Cartella destinazione CSV')
        if not parent:return
        folder=Path(parent)/('MIC_GTFS_conflitti_'+uuid.uuid4().hex[:10]);folder.mkdir();timezone=self.result['config']['timezone']
        for key,title in TABLES:
            rows=self.result[key];keys=list(dict.fromkeys(k for row in rows for k in row)) or ['area_id','note']
            with (folder/(key+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader()
                for row in rows:writer.writerow({k:display_value(k,row.get(k),timezone) for k in keys})
        (folder/'analysis.json').write_text(json.dumps(self.result['config'],ensure_ascii=False,indent=2),encoding='utf-8');self.info.setText('Tabelle CSV complete e configurazione salvate.')
