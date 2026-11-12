"""QGIS presentation and export; called on GUI thread only."""
import datetime as dt,json
from zoneinfo import ZoneInfo
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsVectorLayer,QgsField,QgsFeature,QgsGeometry,QgsPointXY,QgsMarkerSymbol,QgsCategorizedSymbolRenderer,QgsRendererCategory

TIME_FIELDS={'start','end','arrival','departure'}
TABLES=[('summary','Sintesi aree'),('bins','Indicatori per fascia'),('events','Passaggi'),('episodes','Episodi di superamento'),('segments','Segmenti occupazione'),('relations','Relazioni segmenti-passaggi'),('diagnostics','Diagnostica')]

def display_value(key,value,timezone):
    if value is None:return ''
    if key in TIME_FIELDS:return dt.datetime.fromtimestamp(value,ZoneInfo(timezone)).isoformat()
    if isinstance(value,(list,dict)):return json.dumps(value,ensure_ascii=False)
    return str(value)

def build_layers(result,stops):
    layers=[];timezone=result['config']['timezone']
    for kind,title in TABLES:
        rows=result[kind];keys=list(dict.fromkeys(k for row in rows for k in row)) or ['area_id','note']
        if kind=='summary':keys+=['map_status']
        layer=QgsVectorLayer('Point?crs=EPSG:4326' if kind=='summary' else 'None',title,'memory');provider=layer.dataProvider();fields=[]
        for key in keys:
            values=[r[key] for r in rows if r.get(key) is not None]
            typ=QVariant.LongLong if values and all(isinstance(v,int) and not isinstance(v,bool) for v in values) and key not in TIME_FIELDS else QVariant.Double if values and all(isinstance(v,(int,float)) for v in values) and key not in TIME_FIELDS else QVariant.String
            fields.append(QgsField(key,typ))
        provider.addAttributes(fields);layer.updateFields();features=[]
        for row in rows:
            r=dict(row)
            if kind=='summary':r['map_status']='dati incompleti' if r.get('excluded_reported') else 'capacita non definita' if r.get('capacity') is None else 'superamento' if r['exceed_seconds'] else 'nessun superamento nel modello'
            f=QgsFeature(layer.fields());attrs=[]
            for field in fields:
                value=r.get(field.name());attrs.append(None if value is None else display_value(field.name(),value,timezone) if field.type()==QVariant.String else value)
            f.setAttributes(attrs)
            if kind=='summary':
                ids=[sid for sid,area in result['config']['stop_areas'].items() if area==r['area_id']];coords=[]
                for sid in ids:
                    try:coords.append((float(stops[sid]['stop_lon']),float(stops[sid]['stop_lat'])))
                    except (KeyError,ValueError,TypeError):pass
                if coords:f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(sum(x for x,y in coords)/len(coords),sum(y for x,y in coords)/len(coords))))
            features.append(f)
        if features:
            ok,_=provider.addFeatures(features)
            if not ok:raise ValueError('Creazione risultati fallita: '+title)
        layer.updateExtents();layer.setCustomProperty('MIC_GTFS/analysis_id',result['config']['analysis_id']);layer.setAbstract('SCENARIO PROGRAMMATO. Conteggio visite GTFS, non misura veicoli fisici o code. Stalli indipendenti; stalli in linea richiedono verifica. '+json.dumps(result['config'],ensure_ascii=False))
        if kind=='summary':
            categories=[]
            for label,color in [('dati incompleti','#888888'),('capacita non definita','#3979aa'),('superamento','#c83b32'),('nessun superamento nel modello','#24856b')]:
                symbol=QgsMarkerSymbol.createSimple({'name':'circle','color':color,'size':'4'});categories.append(QgsRendererCategory(label,symbol,label))
            layer.setRenderer(QgsCategorizedSymbolRenderer('map_status',categories))
        layers.append((kind,layer))
    return layers
