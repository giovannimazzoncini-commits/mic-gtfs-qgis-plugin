import os,csv,io,zipfile,datetime,collections,hashlib,json,re,uuid,html
from .engine import seconds,active,search,connection,project_ordered,clip
from qgis.PyQt.QtWidgets import QAction,QDockWidget,QWidget,QFrame,QVBoxLayout,QHBoxLayout,QFormLayout,QPushButton,QLabel,QFileDialog,QComboBox,QSpinBox,QDateEdit,QMessageBox,QApplication,QCheckBox,QProgressDialog,QLineEdit,QTreeWidget,QTreeWidgetItem,QTabWidget,QScrollArea,QToolButton,QButtonGroup,QInputDialog
from qgis.PyQt.QtCore import QVariant,QDate,Qt,QSize
from qgis.PyQt.QtGui import QColor,QIcon
from qgis.core import QgsVectorLayer,QgsField,QgsFeature,QgsGeometry,QgsPointXY,QgsProject,QgsLineSymbol,QgsVectorFileWriter,QgsLayerDefinition

def classFactory(iface):return Plugin(iface)
class Cancelled(Exception):pass
class Plugin:
 def __init__(self,iface):
  self.iface=iface;self.data={};self.busy=False;self.cache={};self.display=[];self.network=None;self.groups={};self.solutions={};self.detail_layers=[];self.metadata={};self.stopid=None
 def initGui(self):
  self.action=QAction(QIcon(os.path.join(os.path.dirname(__file__),'icon.svg')),'MIC_GTFS',self.iface.mainWindow());self.action.setCheckable(True);self.action.toggled.connect(self.toggle);self.iface.addPluginToMenu('MIC_GTFS',self.action);self.iface.addToolBarIcon(self.action);QgsProject.instance().cleared.connect(self.reset_state)
 def unload(self):
  if hasattr(self,'conflicts_panel'):self.conflicts_panel.dispose()
  try:QgsProject.instance().cleared.disconnect(self.reset_state)
  except (TypeError,RuntimeError):pass
  self.iface.removePluginMenu('MIC_GTFS',self.action);self.iface.removeToolBarIcon(self.action)
  if hasattr(self,'dock'):self.iface.removeDockWidget(self.dock);self.dock.deleteLater()
 def reset_state(self):
  if hasattr(self,'conflicts_panel'):self.conflicts_panel.invalidate_feed()
  self.display=[];self.detail_layers=[];self.network=None;self.groups={};self.solutions={};self.stopid=None
  if hasattr(self,'tree'):self.tree.clear();self.metrics.setText('Nessuna analisi disponibile');self.status.setText('Progetto chiuso · reimporta il feed');self.selection_changed()
 def stoplayer(self):
  return QgsProject.instance().mapLayer(self.stopid) if self.stopid else None
 def dir_label(self,reverse,origin):return ('Verso la ' if reverse else 'Dalla ')+origin
 def toggle(self,visible):
  if not hasattr(self,'dock'):self.build()
  self.dock.setVisible(visible)
  if visible:self.dock.raise_()
 def sync(self,visible):
  self.action.blockSignals(True);self.action.setChecked(visible);self.action.blockSignals(False)
 def label(self,text,kind=None):
  l=QLabel(text);l.setWordWrap(True)
  if kind:l.setProperty('kind',kind)
  return l
 def card(self,parent):
  frame=QFrame();frame.setProperty('card',True);layout=QVBoxLayout(frame);layout.setContentsMargins(13,12,13,12);layout.setSpacing(8);parent.addWidget(frame);return frame,layout
 def button(self,parent,text,fn,primary=False):
  b=QPushButton(text);b.clicked.connect(lambda:self.run(fn));parent.addWidget(b);self.buttons.append(b)
  if primary:b.setProperty('primary',True)
  return b
 def segments(self,parent,labels,callback):
  row=QHBoxLayout();row.setSpacing(5);group=QButtonGroup(self.dock);group.setExclusive(True);buttons=[]
  for index,text in enumerate(labels):
   b=QPushButton(text);b.setCheckable(True);group.addButton(b,index);row.addWidget(b);buttons.append(b);b.clicked.connect(lambda checked,i=index:callback(i))
  buttons[0].setChecked(True);parent.addLayout(row);return group,buttons
 def build(self):
  self.dock=QDockWidget('MIC_GTFS',self.iface.mainWindow());self.dock.setObjectName('MIC_GTFS_Dock');self.dock.setAllowedAreas(Qt.LeftDockWidgetArea|Qt.RightDockWidgetArea);self.dock.setMinimumWidth(350);self.dock.visibilityChanged.connect(self.sync)
  body=QWidget();body.setObjectName('MICBody');body.setStyleSheet(open(os.path.join(os.path.dirname(__file__),'style.qss'),encoding='utf-8').read());outer=QVBoxLayout(body);outer.setContentsMargins(14,12,14,12);outer.setSpacing(5)
  brand=self.label('MIC_GTFS');brand.setObjectName('brand');outer.addWidget(brand);outer.addWidget(self.label('Accessibilità del trasporto pubblico','muted'))
  self.tabs=QTabWidget();outer.addWidget(self.tabs,1);self.buttons=[]
  scroll=QScrollArea();scroll.setWidgetResizable(True);page=QWidget();a=QVBoxLayout(page);a.setContentsMargins(0,12,0,0);a.setSpacing(12);scroll.setWidget(page);self.tabs.addTab(scroll,'Analisi')
  _,c=self.card(a);c.addWidget(self.label('FEED GTFS','section'));self.feedlabel=self.label('Nessun feed importato');c.addWidget(self.feedlabel);self.feedstate=self.label('Seleziona un archivio ZIP locale.','muted');c.addWidget(self.feedstate);self.button(c,'Importa / cambia feed…',self.load)
  _,c=self.card(a);c.addWidget(self.label('FERMATA SELEZIONATA','section'));self.selected=self.label('Seleziona una fermata sulla mappa');self.selected.setStyleSheet('font-size:15px;font-weight:600;');c.addWidget(self.selected);self.stopcode=self.label('Usa il layer delle fermate MIC_GTFS.','muted');c.addWidget(self.stopcode)
  _,c=self.card(a);c.addWidget(self.label('ANALISI','section'));self.mode=QComboBox();self.mode.addItems(['Raggiungibilità','Percorsi completi e varianti','Passaggi giornalieri']);c.addWidget(self.mode)
  self.routebox=QWidget();r=QVBoxLayout(self.routebox);r.setContentsMargins(0,5,0,0);r.setSpacing(10);r.addWidget(self.label('Direzione'));self.direction,self.dirbuttons=self.segments(r,['Da qui','Verso qui','Entrambe'],lambda i:None)
  r.addWidget(self.label('Tempo massimo'));self.timegroup,self.timebuttons=self.segments(r,['10 min','15 min','20 min','Altro'],self.choose_time)
  self.minutes=QSpinBox();self.minutes.setRange(1,240);self.minutes.setValue(10);self.minutes.setSuffix(' minuti');self.minutes.hide();r.addWidget(self.minutes)
  r.addWidget(self.label('Cambi'));self.changegroup,self.changebuttons=self.segments(r,['Nessuno','Massimo 1'],lambda i:None);c.addWidget(self.routebox)
  self.summary=self.label('','muted');c.addWidget(self.summary)
  self.advanced=QToolButton();self.advanced.setText('Parametri avanzati');self.advanced.setCheckable(True);self.advanced.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);self.advanced.setArrowType(Qt.RightArrow);c.addWidget(self.advanced)
  self.advbox=QWidget();av=QFormLayout(self.advbox);av.setContentsMargins(0,0,0,0);av.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
  self.date=QDateEdit();self.date.setCalendarPopup(True);self.date.setDate(QDate.currentDate());av.addRow('Data',self.date)
  self.period=QComboBox();self.period.addItems(['Feriale · lun–ven','Data singola']);av.addRow('Servizio',self.period)
  self.buffer=QSpinBox();self.buffer.setRange(0,60);self.buffer.setValue(2);self.buffer.setSuffix(' min');av.addRow('Cambio minimo',self.buffer)
  self.saving=QSpinBox();self.saving.setRange(0,60);self.saving.setValue(1);self.saving.setSuffix(' min');av.addRow('Vantaggio cambio >',self.saving)
  self.tolerance=QSpinBox();self.tolerance.setRange(10,1000);self.tolerance.setValue(150);self.tolerance.setSuffix(' m circa');av.addRow('Tolleranza shape',self.tolerance)
  self.all=QCheckBox('Tutta la rete, senza selezione');av.addRow(self.all);self.filter=QCheckBox('Applica periodo ai percorsi completi');av.addRow(self.filter)
  self.advbox.hide();self.advanced.toggled.connect(self.advbox.setVisible);self.advanced.toggled.connect(lambda checked:self.advanced.setArrowType(Qt.DownArrow if checked else Qt.RightArrow));c.addWidget(self.advbox)
  _,c=self.card(a);c.addWidget(self.label('SALVATAGGIO','section'));self.autosave=QCheckBox('Salva su file dopo il calcolo');c.addWidget(self.autosave);self.format=QComboBox();self.format.addItems(['GeoPackage (.gpkg)','Shapefile (.shp)']);c.addWidget(self.format);c.addWidget(self.label('Se disattivato, i risultati restano temporanei.','muted'))
  self.button(a,'Calcola raggiungibilità',self.calculate,True);self.calcbutton=self.buttons[-1];a.addStretch()
  results=QWidget();rv=QVBoxLayout(results);rv.setContentsMargins(0,12,0,0);rv.setSpacing(10);self.tabs.addTab(results,'Collegamenti')
  self.metrics=self.label('Nessuna analisi disponibile');self.metrics.setStyleSheet('font-size:14px;font-weight:600;');rv.addWidget(self.metrics)
  self.find=QLineEdit();self.find.setPlaceholderText('Cerca linea, cambio o fermata…');self.find.setClearButtonEnabled(True);rv.addWidget(self.find)
  self.tree=QTreeWidget();self.tree.setHeaderHidden(True);self.tree.setIndentation(14);self.tree.setAnimated(True);self.tree.setUniformRowHeights(False);rv.addWidget(self.tree,1)
  self.tree.currentItemChanged.connect(self.selection_info);self.tree.itemDoubleClicked.connect(lambda *args:self.run(self.itinerary));self.find.textChanged.connect(self.filter_tree)
  _,c=self.card(rv);c.addWidget(self.label('COLLEGAMENTO SELEZIONATO','section'));self.selectiontitle=self.label('Scegli un collegamento o una fermata');c.addWidget(self.selectiontitle);self.selectionsubtitle=self.label('','muted');c.addWidget(self.selectionsubtitle)
  self.only=QCheckBox('Mostra solo questo itinerario');self.only.setChecked(True);c.addWidget(self.only);self.button(c,'Mostra sulla mappa',self.itinerary,True);self.button(c,'Ripristina rete',self.restore)
  self.details=self.label('Seleziona una fermata per un viaggio con data e orari.','muted');c.addWidget(self.details)
  self.scope=QComboBox();self.scope.addItems(['Tutta l’ultima analisi','Collegamento selezionato','Itinerario visualizzato']);rv.addWidget(self.scope);self.button(rv,'Salva risultati…',self.export_selected)
  from .occupancy_ui import ConflictsPanel
  self.conflicts_panel=ConflictsPanel(self);self.tabs.addTab(self.conflicts_panel,'Conflitti fermata')
  self.status=self.label('Pronto · dati elaborati localmente','muted');outer.addWidget(self.status)
  self.mode.currentIndexChanged.connect(self.update);self.date.dateChanged.connect(self.update);self.period.currentIndexChanged.connect(self.update);self.update()
  self.dock.setWidget(body);self.iface.addDockWidget(Qt.RightDockWidgetArea,self.dock);self.dock.resize(430,850)
 def choose_time(self,index):
  if index<3:self.minutes.setValue([10,15,20][index])
  self.minutes.setVisible(index==3)
 def update(self,*args):
  m=self.mode.currentIndex();self.routebox.setVisible(m==0)
  for w in [self.buffer,self.saving]:w.setEnabled(m==0)
  self.all.setEnabled(m==1);self.filter.setEnabled(m==1)
  self.calcbutton.setText(['Calcola raggiungibilità','Carica percorsi e varianti','Calcola passaggi giornalieri'][m]);dates=self.dates();self.summary.setText(('Feriale · giornata intera' if self.period.currentIndex()==0 else 'Giornata selezionata')+'\n'+str(dates[0])+' → '+str(dates[-1])+('\nAttesa iniziale esclusa' if m==0 else ''))
 def tick(self):
  QApplication.processEvents()
  if self.progress.wasCanceled():raise Cancelled()
 def run(self,fn):
  if self.busy:return
  self.busy=True
  for b in self.buttons:b.setEnabled(False)
  self.progress=QProgressDialog('MIC_GTFS · elaborazione…','Annulla',0,0,self.iface.mainWindow());self.progress.setMinimumDuration(0);self.progress.show();self.status.setText('Elaborazione in corso…')
  try:fn()
  except Cancelled:self.status.setText('Annullato · eventuali risultati parziali da non utilizzare')
  except Exception as e:
   self.status.setText('Operazione non completata');QMessageBox.warning(self.iface.mainWindow(),'MIC_GTFS',str(e))
  finally:
   self.progress.close();self.busy=False
   for b in self.buttons:b.setEnabled(True)
 def load(self):
  path,_=QFileDialog.getOpenFileName(self.iface.mainWindow(),'Importa GTFS','','ZIP (*.zip)')
  if not path:return
  data={}
  with zipfile.ZipFile(path) as z:
   mapping={n.rsplit('/',1)[-1].lower():n for n in z.namelist() if not n.endswith('/')}
   for table in ['agency','stops','trips','routes','stop_times','shapes','calendar','calendar_dates','transfers','frequencies']:
    if table+'.txt' not in mapping:continue
    rows=[]
    for n,r in enumerate(csv.DictReader(io.TextIOWrapper(z.open(mapping[table+'.txt']),encoding='utf-8-sig',newline=''))):
     rows.append(r)
     if n%25000==0:self.tick()
    data[table]=rows
  if not all(data.get(t) for t in ['stops','trips','stop_times']):raise ValueError('Mancano stops/trips/stop_times.')
  if hasattr(self,'conflicts_panel'):self.conflicts_panel.invalidate_feed()
  self.restore();self.data=data;self.feedpath=path;self.stops={r['stop_id']:r for r in data['stops']};self.trips={r['trip_id']:r for r in data['trips']};self.routes={r['route_id']:r for r in data.get('routes',[])};self.seq=collections.defaultdict(list);self.shapes=collections.defaultdict(list)
  for r in data['stop_times']:self.seq[r['trip_id']].append(r)
  for s in self.seq.values():s.sort(key=lambda r:int(r['stop_sequence']))
  for r in data.get('shapes',[]):self.shapes[r['shape_id']].append(r)
  for s in self.shapes.values():s.sort(key=lambda r:int(r['shape_pt_sequence']))
  self.cache={};self.solutions={};self.groups={};self.tree.clear();l=self.points('MIC_GTFS — fermate feed',[(s,0) for s in self.stops],'value');self.stopid=l.id();l.selectionChanged.connect(self.selection_changed)
  self.feedlabel.setText(os.path.basename(path));self.feedstate.setText(str(len(self.stops))+' fermate · '+str(len(self.shapes))+' tracciati');self.status.setText('Feed importato · seleziona una fermata');self.selection_changed()
 def selection_changed(self,*args):
  l=self.stoplayer()
  if l is None:self.selected.setText('Seleziona una fermata sulla mappa');self.stopcode.setText('Importa un feed: layer fermate MIC_GTFS non presente');return
  fs=l.selectedFeatures()
  if len(fs)==1:self.selected.setText(str(fs[0]['stop_name']));self.stopcode.setText('Codice '+str(fs[0]['stop_id']))
  else:self.selected.setText('Seleziona una fermata' if not fs else str(len(fs))+' fermate selezionate');self.stopcode.setText('Selezione sul layer fermate MIC_GTFS')
 def point(self,sid):
  r=self.stops[sid];return float(r['stop_lon']),float(r['stop_lat'])
 def layer(self,name,geometry,fields,rows,group=None):
  l=QgsVectorLayer(geometry+'?crs=EPSG:4326',name,'memory');p=l.dataProvider();p.addAttributes([QgsField(n,t) for n,t in fields]);l.updateFields();fs=[]
  for g,a in rows:
   f=QgsFeature(l.fields());f.setGeometry(g);f.setAttributes(a);fs.append(f)
  p.addFeatures(fs);l.updateExtents();QgsProject.instance().addMapLayer(l,group is None)
  if group is not None:group.addLayer(l)
  return l
 def points(self,name,items,field,group=None):
  rows=[]
  for sid,value in items:
   try:rows.append((QgsGeometry.fromPointXY(QgsPointXY(*self.point(sid))),[sid,self.stops[sid].get('stop_name',''),value]))
   except (KeyError,ValueError):pass
  return self.layer(name,'Point',[('stop_id',QVariant.String),('stop_name',QVariant.String),(field,QVariant.Double)],rows,group)
 def dates(self):
  q=self.date.date();d=datetime.date(q.year(),q.month(),q.day());return [d] if self.period.currentIndex() else [d-datetime.timedelta(days=d.weekday())+datetime.timedelta(days=i) for i in range(5)]
 def rid(self,tid):return self.trips[tid]['route_id']
 def line(self,rid):return self.routes.get(rid,{}).get('route_short_name') or rid
 def color(self,rid):return QColor.fromHsv(int(hashlib.sha256(rid.encode()).hexdigest()[:8],16)%360,195,185).name()
 def style(self,l,rid,second=False,width=1):
  l.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color':self.color(rid),'line_width':str(width),'line_style':'dash' if second else 'solid'}));l.triggerRepaint()
 def geometry(self,tid,i,j):
  seq=self.seq[tid];sid=self.trips[tid].get('shape_id','');shape=self.shapes.get(sid,[])
  if len(shape)<2:raise ValueError('Shape assente')
  poly=[(float(r['shape_pt_lon']),float(r['shape_pt_lat'])) for r in shape]
  try:
   a,b=float(seq[i]['shape_dist_traveled']),float(seq[j]['shape_dist_traveled']);cum=[float(r['shape_dist_traveled']) for r in shape]
   if any(y<x for x,y in zip(cum,cum[1:])):raise ValueError()
   pts=clip(poly,cum,a,b);source='shape_dist'
  except (KeyError,TypeError,ValueError):
   key=(sid,tuple(r['stop_id'] for r in seq),self.tolerance.value())
   if key not in self.cache:
    try:self.cache[key]=project_ordered(poly,[self.point(r['stop_id']) for r in seq],self.tolerance.value(),self.tick)
    except (ValueError,KeyError) as e:self.cache[key]=str(e)
   result=self.cache[key]
   if isinstance(result,str):raise ValueError(result)
   cum,positions=result;pts=clip(poly,cum,positions[i],positions[j]);source='shape_proj'
  return QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in pts]),source
 def connection_label(self,ck):
  routes,stop=ck;names=' → '.join(self.line(r) for r in routes)
  return names+' — cambio a '+self.stops.get(stop,{}).get('stop_name',stop)+' ['+stop+']' if stop else 'Solo '+names+' — senza cambio'
 def badge_row(self,routes,subtitle,item):
  w=QFrame();w.setProperty('card',True);lay=QVBoxLayout(w);lay.setContentsMargins(9,8,9,8);lay.setSpacing(5);row=QHBoxLayout();row.setSpacing(5)
  for i,rid in enumerate(routes):
   if i:row.addWidget(QLabel('→'))
   badge=QLabel(html.escape(self.line(rid)));badge.setTextFormat(Qt.PlainText);badge.setStyleSheet('QLabel {background:'+self.color(rid)+';color:white;padding:3px 7px;border-radius:5px;font-weight:600;}');row.addWidget(badge)
  row.addStretch();lay.addLayout(row);sub=self.label(subtitle,'muted');lay.addWidget(sub);w.setAttribute(Qt.WA_TransparentForMouseEvents,True);self.tree.setItemWidget(item,0,w);item.setSizeHint(0,QSize(220,70));item.setToolTip(0,subtitle)
 def calculate(self):
  if not self.data:raise ValueError('Importa feed.')
  stops=self.stoplayer()
  if stops is None:raise ValueError('Il layer «MIC_GTFS — fermate feed» è stato rimosso: reimporta il feed.')
  ids={str(f['stop_id']) for f in stops.selectedFeatures()};mode=self.mode.currentIndex();dates=self.dates()
  if mode==1 and self.all.isChecked():ids=set()
  elif not ids:raise ValueError('Seleziona fermate nel layer del feed MIC_GTFS.')
  self.metadata={'feed':getattr(self,'feedpath',''),'dates':[str(d) for d in dates],'mode':mode,'minutes':self.minutes.value(),'max_changes':self.changegroup.checkedId(),'direzione':['da','verso','entrambe'][max(0,self.direction.checkedId())],'min_transfer':self.buffer.value(),'saving':self.saving.value(),'tolerance':self.tolerance.value()}
  if mode==1:self.fullpaths(ids,dates);self.finish();return
  if self.data.get('frequencies'):raise ValueError('frequencies.txt non supportato.')
  days=[(d,active(self.data,d)) for d in dates]
  if not any(a for d,a in days):raise ValueError('Nessun servizio: scegliere data coperta dal feed.')
  if mode==2:
   count=collections.Counter()
   for d,a in days:
    for tid in a:
     for r in self.seq.get(tid,[]):
      if r['stop_id'] in ids:count[r['stop_id']]+=1
   self.restore();self.solutions={};self.tree.clear();self.network=QgsProject.instance().layerTreeRoot().addGroup('MIC_GTFS — passaggi '+str(dates[0]));self.groups={};self.points('Passaggi medi giornalieri',[(s,count[s]/len(dates)) for s in ids],'pass_gior',self.network);self.metrics.setText(str(len(ids))+' fermate · passaggi medi al giorno');self.finish();return
  if len(ids)!=1:raise ValueError('Una sola fermata per raggiungibilita.')
  if self.changegroup.checkedId() and self.data.get('transfers'):raise ValueError('Cambi bloccati: transfers.txt non supportato.')
  origin=next(iter(ids));choice=self.direction.checkedId();dirs=[False,True] if choice==2 else [choice==1];both=len(dirs)==2;minutes=self.minutes.value();solutions={};parts=collections.defaultdict(lambda:collections.defaultdict(set))
  for day,a in days:
   for reverse in dirs:
    kept=search(self.seq,a,origin,minutes*60,self.changegroup.checkedId(),self.buffer.value()*60,reverse,self.saving.value()*60,self.tick)
    for sid,duration,legs in kept:
     ck=connection(legs,self.trips,self.seq);key=(reverse,sid,ck)
     if key not in solutions or duration<solutions[key][0]:solutions[key]=(duration,day,legs)
     for k,(tid,i,j) in enumerate(legs):
      for index in range(i,j):parts[(reverse,ck)][k].add((tid,index))
    self.tick()
  self.restore();self.solutions=solutions;self.groups={};self.tree.clear();treeparents={};treesub={};best={r:{} for r in dirs}
  self.network=QgsProject.instance().layerTreeRoot().addGroup('MIC_GTFS — '+str(minutes)+' min — '+('DA/VERSO' if both else ('VERSO' if dirs[0] else 'DALLA'))+' '+origin);parents={};errors=[]
  dirnodes={r:(self.network.addGroup(self.dir_label(r,origin)) if both else self.network) for r in dirs}
  fields=[('route_id',QVariant.String),('linea',QVariant.String),('trip_id',QVariant.String),('da_stop',QVariant.String),('a_stop',QVariant.String),('geometria',QVariant.String),('camb_stop',QVariant.String)]
  for n,gk in enumerate(sorted(parts)):
   reverse,ck=gk;routes,transfer=ck;first=routes[0]
   if (reverse,first) not in parents:parents[(reverse,first)]=dirnodes[reverse].addGroup('Partenza con linea '+self.line(first)+' ['+first+']')
   subgroup=parents[(reverse,first)].addGroup(self.connection_label(ck));self.groups[gk]=subgroup;subgroup.setExpanded(False)
   for k in sorted(parts[gk]):
    rows=[]
    for tid,index in sorted(parts[gk][k]):
     try:
      geom,source=self.geometry(tid,index,index+1);a,b=self.seq[tid][index:index+2];rows.append((geom,[self.rid(tid),self.line(self.rid(tid)),tid,a['stop_id'],b['stop_id'],source,transfer]))
     except (ValueError,KeyError) as e:errors.append((tid,index,str(e)))
    l=self.layer(('Prima tratta — ' if k==0 else 'Dopo cambio — ')+'linea '+self.line(routes[k]),'LineString',fields,rows,subgroup);self.style(l,routes[k],k>0)
   if transfer:
    l=self.points('Cambio — '+self.stops.get(transfer,{}).get('stop_name',transfer),[(transfer,0)],'value',subgroup);l.renderer().symbol().setColor(QColor('#ffbf00'));l.renderer().symbol().setSize(4);l.triggerRepaint()
   if n%10==0:self.tick()
  dirtree={r:(QTreeWidgetItem(self.tree,[self.dir_label(r,origin)]) if both else self.tree) for r in dirs}
  for key,(duration,day,legs) in sorted(solutions.items()):
   reverse,sid,ck=key;routes,transfer=ck;first=routes[0];best[reverse][sid]=min(best[reverse].get(sid,duration),duration);pk=(reverse,first);gk=(reverse,ck)
   if pk not in treeparents:treeparents[pk]=QTreeWidgetItem(dirtree[reverse],['Partenza con linea '+self.line(first)])
   if gk not in treesub:
    item=QTreeWidgetItem(treeparents[pk],[' → '.join(self.line(r) for r in routes)]);item.setData(0,Qt.UserRole,{'kind':'group','routes':list(routes),'transfer':transfer,'reverse':reverse});treesub[gk]=item
    subtitle='Cambio: '+self.stops.get(transfer,{}).get('stop_name',transfer) if transfer else 'Senza cambio · collegamento diretto';self.badge_row(routes,subtitle,item)
   leaf=QTreeWidgetItem(treesub[gk],[self.stops[sid].get('stop_name',sid)+' ['+sid+']\n'+str(round(duration/60,1))+' min · '+str(day)]);leaf.setToolTip(0,leaf.text(0));leaf.setData(0,Qt.UserRole,{'kind':'leaf','sid':sid,'routes':list(routes),'transfer':transfer,'reverse':reverse})
  self.tree.expandToDepth(1 if both else 0);self.filter_tree(self.find.text())
  name='Fermate raggiungibili - '+str(minutes)+' min - '+('da e verso la ' if both else ('verso la ' if dirs[0] else 'dalla '))+origin
  if both:
   da,ve=best[False],best[True];rows=[]
   for s in sorted(set(da)|set(ve)):
    try:g=QgsGeometry.fromPointXY(QgsPointXY(*self.point(s)))
    except (KeyError,ValueError):continue
    rows.append((g,[s,self.stops[s].get('stop_name',''),da[s]/60 if s in da else None,ve[s]/60 if s in ve else None,'entrambi' if s in da and s in ve else ('da' if s in da else 'verso')]))
   self.layer(name,'Point',[('stop_id',QVariant.String),('stop_name',QVariant.String),('da_min',QVariant.Double),('verso_min',QVariant.Double),('ambito',QVariant.String)],rows,self.network)
   self.metrics.setText(str(len(rows))+' fermate uniche  ·  '+str(len(da))+' da  ·  '+str(len(ve))+' verso  ·  '+str(len(parts))+' collegamenti')
  else:
   self.points(name,[(s,t/60) for s,t in best[dirs[0]].items()],'min_min',self.network);self.metrics.setText(str(len(best[dirs[0]]))+' fermate  ·  '+str(len(parts))+' collegamenti')
  if errors:self.errors(errors,self.network)
  self.status.setText('Calcolo completato · '+str(len(errors))+' segmenti omessi');self.finish()
 def finish(self):
  self.tabs.setCurrentIndex(1)
  if self.autosave.isChecked():self.export_nodes([self.network])
 def filter_tree(self,text):
  text=text.casefold().strip()
  def apply(item,parentmatch=False):
   data=item.data(0,Qt.UserRole);extra=''
   if data:extra=' '.join(self.line(r) for r in data['routes'])+' '+self.stops.get(data['transfer'],{}).get('stop_name','')
   match=parentmatch or not text or text in (item.text(0)+' '+extra).casefold();visible=match
   for i in range(item.childCount()):visible=apply(item.child(i),match) or visible
   item.setHidden(not visible)
   if text and visible and item.childCount():item.setExpanded(True)
   return visible
  for i in range(self.tree.topLevelItemCount()):apply(self.tree.topLevelItem(i))
 def selection_info(self,item,previous=None):
  data=item.data(0,Qt.UserRole) if item else None
  if not data:self.selectiontitle.setText('Scegli un collegamento o una fermata');self.selectionsubtitle.setText('');return
  routes=tuple(data['routes']);stop=data['transfer'];self.selectiontitle.setText(' → '.join(self.line(r) for r in routes));subtitle='Cambio: '+self.stops.get(stop,{}).get('stop_name',stop) if stop else 'Senza cambio'
  if data['kind']=='leaf':subtitle+='\n'+self.stops[data['sid']].get('stop_name',data['sid'])
  if self.metadata.get('direzione')=='entrambe':subtitle+='\n'+('Verso la fermata selezionata' if data.get('reverse') else 'Dalla fermata selezionata')
  self.selectionsubtitle.setText(subtitle)
 def errors(self,errors,group=None):
  l=QgsVectorLayer('None','MIC_GTFS errori geometria','memory');p=l.dataProvider();p.addAttributes([QgsField('trip_id',QVariant.String),QgsField('indice',QVariant.Int),QgsField('motivo',QVariant.String)]);l.updateFields();fs=[]
  for tid,index,msg in errors:
   f=QgsFeature(l.fields());f.setAttributes([tid,index,msg]);fs.append(f)
  p.addFeatures(fs);QgsProject.instance().addMapLayer(l,group is None)
  if group is not None:group.addLayer(l)
 def restore(self):
  for lid in self.display:
   if QgsProject.instance().mapLayer(lid):QgsProject.instance().removeMapLayer(lid)
  self.display=[];self.detail_layers=[]
  if self.network is not None:
   try:self.network.setItemVisibilityChecked(True)
   except RuntimeError:self.network=None
 def choice(self):
  item=self.tree.currentItem();data=item.data(0,Qt.UserRole) if item else None
  if not data:raise ValueError('Seleziona un collegamento o una fermata nell’albero.')
  return data,(bool(data.get('reverse',False)),(tuple(data['routes']),data['transfer']))
 def itinerary(self):
  data,gk=self.choice();reverse,ck=gk
  if data['kind']!='leaf':raise ValueError('Espandi il collegamento e seleziona una fermata finale.')
  key=(reverse,data['sid'],ck)
  if key not in self.solutions:raise ValueError('Ricalcola rete.')
  duration,day,legs=self.solutions[key];self.restore();texts=[];errors=[];transfer=[]
  for k,(tid,i,j) in enumerate(legs):
   a,b=self.seq[tid][i],self.seq[tid][j];wait=0;rid=self.rid(tid)
   if k:
    pt,pi,pj=legs[k-1];wait=(seconds(a['departure_time'])-seconds(self.seq[pt][pj]['arrival_time']))/60;transfer.append((a['stop_id'],wait))
   try:
    geom,source=self.geometry(tid,i,j);l=self.layer('MIC_GTFS dettaglio — '+self.line(rid),'LineString',[('linea',QVariant.String),('trip_id',QVariant.String),('partenza',QVariant.String),('arrivo',QVariant.String),('data_serv',QVariant.String),('tot_min',QVariant.Double),('att_min',QVariant.Double),('geometria',QVariant.String)],[(geom,[self.line(rid),tid,a['departure_time'],b['arrival_time'],str(day),duration/60,wait,source])]);self.style(l,rid,k>0,1.6);self.display.append(l.id())
   except (ValueError,KeyError) as e:errors.append((tid,i,str(e)))
   texts.append('Linea '+self.line(rid)+' · '+a.get('departure_time','')+' → '+b.get('arrival_time',''))
  if transfer:
   l=self.points('MIC_GTFS dettaglio — cambio',transfer,'att_min');l.renderer().symbol().setColor(QColor('#ffbf00'));l.renderer().symbol().setSize(5);l.triggerRepaint();self.display.append(l.id())
  self.detail_layers=list(self.display)
  if self.only.isChecked() and self.network is not None:
   try:self.network.setItemVisibilityChecked(False)
   except RuntimeError:pass
  if errors:self.errors(errors)
  self.details.setText(str(round(duration/60,1))+' minuti · '+str(day)+'\n'+'\n'.join(texts)+'\nTratti omessi: '+str(len(errors)))
 def fullpaths(self,ids,dates):
  allowed=set().union(*(active(self.data,d) for d in dates)) if self.filter.isChecked() else set(self.trips);variants={}
  for tid in sorted(allowed):
   t=self.trips[tid];seq=self.seq.get(tid,[])
   if ids and not any(r['stop_id'] in ids for r in seq):continue
   key=(t['route_id'],t.get('direction_id',''),t.get('shape_id',''),tuple((r['stop_id'],r.get('pickup_type','') or '0',r.get('drop_off_type','') or '0') for r in seq));variants.setdefault(key,tid)
  self.restore();self.solutions={};self.tree.clear();self.network=QgsProject.instance().layerTreeRoot().addGroup('MIC_GTFS — percorsi completi');self.groups={};byline=collections.defaultdict(list)
  for key,tid in variants.items():
   shape=self.shapes.get(key[2],[])
   if len(shape)<2:continue
   geom=QgsGeometry.fromPolylineXY([QgsPointXY(float(r['shape_pt_lon']),float(r['shape_pt_lat'])) for r in shape]);byline[key[0]].append((geom,[self.line(key[0]),hashlib.sha256(repr(key).encode()).hexdigest()[:16],key[1],key[2]]))
  for rid,rows in sorted(byline.items()):
   l=self.layer('Linea '+self.line(rid)+' ['+rid+']','LineString',[('linea',QVariant.String),('var_id',QVariant.String),('direction',QVariant.String),('shape_id',QVariant.String)],rows,self.network);self.style(l,rid)
  self.metrics.setText(str(len(variants))+' varianti candidate · '+str(len(byline))+' linee');self.status.setText('Percorsi completi · limite minuti non applicato')
 def export_selected(self):
  scope=self.scope.currentIndex();root=QgsProject.instance().layerTreeRoot()
  if scope==0:
   if self.network is None:raise ValueError('Nessuna analisi da salvare.')
   nodes=[self.network]
  elif scope==1:
   data,gk=self.choice()
   if gk not in self.groups:raise ValueError('Collegamento non disponibile.')
   nodes=[self.groups[gk]]
  else:
   nodes=[root.findLayer(lid) for lid in self.detail_layers if QgsProject.instance().mapLayer(lid)];nodes=[n for n in nodes if n is not None]
   if not nodes:raise ValueError('Visualizza prima un itinerario.')
  self.export_nodes(nodes)
 def export_nodes(self,nodes):
  layers=[];seen=set()
  for node in nodes:
   try:candidates=node.findLayers() if hasattr(node,'findLayers') else [node]
   except RuntimeError:raise ValueError('Il gruppo da salvare è stato rimosso dal progetto: ricalcola l’analisi.')
   for n in candidates:
    l=n.layer()
    if l and l.id() not in seen:seen.add(l.id());layers.append(l)
  if not layers:raise ValueError('Nessun layer da salvare.')
  chosen,ok=QInputDialog.getItem(self.iface.mainWindow(),'Salva risultati','Formato',['GeoPackage (.gpkg)','Shapefile (.shp)'],self.format.currentIndex(),False)
  if not ok:return
  gpkg=chosen.startswith('GeoPackage');self.format.setCurrentIndex(0 if gpkg else 1)
  if gpkg:
   path,_=QFileDialog.getSaveFileName(self.iface.mainWindow(),'Nuovo GeoPackage','','GeoPackage (*.gpkg)')
   if not path:return
   if not path.lower().endswith('.gpkg'):path+='.gpkg'
   if os.path.exists(path):raise ValueError('Scegli un nome nuovo: file esistenti non sovrascritti.')
   folder=os.path.dirname(path) or '.';base=os.path.splitext(os.path.basename(path))[0]
  else:
   parent=QFileDialog.getExistingDirectory(self.iface.mainWindow(),'Cartella destinazione')
   if not parent:return
   base='MIC_GTFS_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:4];folder=os.path.join(parent,base);os.makedirs(folder);path=folder
  manifest=[];pending=[]
  for i,l in enumerate(layers):
   self.tick();name='mic_'+str(i+1).zfill(3)+'_'+re.sub('[^A-Za-z0-9_]','_',l.name())[:45];target=path if gpkg else os.path.join(folder,name+('.shp' if l.isSpatial() else '.dbf'))
   opts=QgsVectorFileWriter.SaveVectorOptions();opts.driverName='GPKG' if gpkg else 'ESRI Shapefile';opts.fileEncoding='UTF-8';opts.layerName=name
   if gpkg:opts.actionOnExistingFile=QgsVectorFileWriter.CreateOrOverwriteFile if i==0 else QgsVectorFileWriter.CreateOrOverwriteLayer
   result=QgsVectorFileWriter.writeAsVectorFormatV3(l,target,QgsProject.instance().transformContext(),opts)
   if result[0]!=QgsVectorFileWriter.NoError:raise ValueError('Scrittura '+l.name()+': '+str(result[1])+'. Output parziali possibili, originali mantenuti.')
   source=target+'|layername='+name if gpkg else target;check=QgsVectorLayer(source,name,'ogr')
   if not check.isValid():raise ValueError('Output non riapribile: '+target)
   pending.append((l,source,l.renderer().clone() if l.renderer() else None));manifest.append({'layer':l.name(),'table':name,'source':source,'fields':[f.name() for f in l.fields()]})
  for l,source,renderer in pending:
   l.setDataSource(source,l.name(),'ogr')
   if renderer:l.setRenderer(renderer)
   l.triggerRepaint()
   if not gpkg:l.saveNamedStyle(os.path.splitext(source)[0]+'.qml')
  qlr=os.path.join(folder,base+'_'+uuid.uuid4().hex[:4]+'.qlr');outcome=QgsLayerDefinition.exportLayerDefinition(qlr,nodes)
  with open(os.path.splitext(qlr)[0]+'_manifest.json','w',encoding='utf-8') as f:json.dump({'plugin':'MIC_GTFS','format':'GPKG' if gpkg else 'Shapefile','parameters':self.metadata,'layers':manifest},f,ensure_ascii=False,indent=2)
  ids={l.id() for l in layers};self.display=[i for i in self.display if i not in ids];self.detail_layers=[i for i in self.detail_layers if i not in ids]
  message=str(len(layers))+' layer salvati e collegati ai file. Salva anche il progetto QGIS. Gruppi e stili nel QLR.'
  if isinstance(outcome,tuple) and not outcome[0]:message+='\nAttenzione QLR: '+str(outcome)
  self.status.setText('Salvataggio completato');QMessageBox.information(self.iface.mainWindow(),'MIC_GTFS',message)
