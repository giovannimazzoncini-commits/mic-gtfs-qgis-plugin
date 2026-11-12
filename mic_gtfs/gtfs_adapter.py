"""Scheduled GTFS adapter; explicit timezone and assumptions."""
import datetime as dt,math
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo=None
from .conflicts import analyse

def parse_seconds(value):
    try:
        h,m,s=map(int,value.split(':'))
        if h<0 or not 0<=m<60 or not 0<=s<60:return None
        return h*3600+m*60+s
    except (AttributeError,ValueError,TypeError):return None

def active_services(data,day):
    key=day.strftime('%Y%m%d');weekday=['monday','tuesday','wednesday','thursday','friday','saturday','sunday'][day.weekday()]
    result={r['service_id'] for r in data.get('calendar',[]) if r.get('start_date','')<=key<=r.get('end_date','') and r.get(weekday)=='1'}
    for r in data.get('calendar_dates',[]):
        if r.get('date')==key:
            if r.get('exception_type')=='1':result.add(r['service_id'])
            elif r.get('exception_type')=='2':result.discard(r['service_id'])
    return result

def local_instant(day,clock,tz):
    naive=dt.datetime.combine(day,dt.time.fromisoformat(clock));values=set()
    for fold in (0,1):
        aware=naive.replace(tzinfo=tz,fold=fold);stamp=int(aware.timestamp())
        if dt.datetime.fromtimestamp(stamp,tz).replace(tzinfo=None)==naive:values.add(stamp)
    if len(values)!=1:raise ValueError('Ora locale ambigua o inesistente nel cambio ora legale: '+str(naive))
    return values.pop()

def calculate(data,cfg,cancel=None):
    if ZoneInfo is None:raise ValueError('Richiesto Python 3.9+ con zoneinfo per questa analisi')
    try:tz=ZoneInfo(cfg['timezone'])
    except Exception as e:raise ValueError('Fuso orario non disponibile: '+cfg['timezone']+'. Verificare banca dati dei fusi del Python QGIS.') from e
    if data.get('frequencies'):raise ValueError('frequencies.txt non supportato in questa build: nessun orario puntuale inventato.')
    day=dt.date.fromisoformat(cfg['date']);start=local_instant(day,cfg['from'],tz);endday=day+dt.timedelta(days=1) if cfg['to']<=cfg['from'] else day;end=local_instant(endday,cfg['to'],tz)
    rows=data['rows'];maxsecs=max((parse_seconds(r.get('arrival_time')) or 0 for r in rows),default=0)
    maxdep=max((parse_seconds(r.get('departure_time')) or 0 for r in rows),default=0)
    lookback=math.ceil((max(maxsecs,maxdep)+cfg['dwell']+cfg['clearance'])/86400)+1
    if lookback>15:raise ValueError('Orari GTFS o durate anomali: oltre 15 giorni. Controllare il feed.')
    areas=cfg['stop_areas'];events=[];diagnostics=[]
    for delta in range(-lookback,2):
        service_day=day+dt.timedelta(days=delta);services=active_services(data,service_day)
        # GTFS time origin: local noon minus twelve elapsed hours.
        base=int(dt.datetime.combine(service_day,dt.time(12),tzinfo=tz).timestamp())-43200
        for i,r in enumerate(rows):
            if cancel and i%500==0 and cancel():raise InterruptedError('Annullato')
            trip=data['trips'].get(r['trip_id'],{})
            if trip.get('service_id') not in services:continue
            a=parse_seconds(r.get('arrival_time'));d=parse_seconds(r.get('departure_time'));sid=r['stop_id'];area=areas[sid]
            ident='|'.join([service_day.isoformat(),r['trip_id'],str(r.get('stop_sequence','')),sid])
            if a is None:
                if service_day==day:diagnostics.append({'area_id':area,'event_id':ident,'reason':'Arrivo mancante/non valido: evento escluso'})
                continue
            if d is not None and d<a:
                if start<=base+a<end:diagnostics.append({'area_id':area,'event_id':ident,'reason':'Partenza prima dell’arrivo: evento escluso'})
                continue
            observed_span=cfg['use_departure'] and d is not None and d>a
            finish=base+d if observed_span else base+a+cfg['dwell'];finish+=cfg['clearance']
            arrival=base+a
            if arrival>=end or finish<=start:continue
            rid=trip.get('route_id','');route=data['routes'].get(rid,{})
            events.append({'event_id':ident,'area_id':area,'stop_id':sid,'trip_id':r['trip_id'],'stop_sequence':r.get('stop_sequence',''),'route_id':rid,'line':route.get('route_short_name') or rid,'service_date':service_day.isoformat(),'arrival':arrival,'start':arrival,'end':finish,'departure':base+d if d is not None else None,'source':'scheduled','occupancy_basis':'arrivo-partenza programmati + liberazione' if observed_span else 'durata assunta + liberazione','timepoint':r.get('timepoint','')})
    result=analyse(events,start,end,cfg['capacity'],cfg['bin_minutes']*60,cancel)
    present={r['area_id'] for r in result['summary']}
    for area in sorted(set(areas.values())-present):
        result['summary'].append({'area_id':area,'start':start,'end':end,'passages':0,'capacity':cfg['capacity'],'peak':0,'overlap_seconds':0,'exceed_seconds':0 if cfg['capacity'] is not None else None,'max_excess':0 if cfg['capacity'] is not None else None,'excess_stall_seconds':0 if cfg['capacity'] is not None else None,'episodes':0 if cfg['capacity'] is not None else None})
        lo=start
        while lo<end:
            hi=min(end,lo+cfg['bin_minutes']*60);entry=dict(result['summary'][-1]);entry.pop('episodes');entry.update(start=lo,end=hi);result['bins'].append(entry);lo=hi
    for row in result['summary']:
        row['excluded_reported']=sum(d['area_id']==row['area_id'] for d in diagnostics)
        row['status']='incompleto: verificare diagnostica' if row['excluded_reported'] else 'scenario programmato; copertura osservata non disponibile'
    result['diagnostics']=diagnostics;result['config']=dict(cfg);result['window']={'start':start,'end':end};return result
