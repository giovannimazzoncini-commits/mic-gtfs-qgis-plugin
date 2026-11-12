"""Half-open occupancy intervals. No Qt/QGIS dependencies."""
from collections import defaultdict

def analyse(events,start,end,capacity=None,bin_seconds=3600,cancel=None):
    if end<=start:raise ValueError('Intervallo temporale non valido')
    if bin_seconds<=0:raise ValueError('Aggregazione non valida')
    if capacity is not None and capacity<1:raise ValueError('Stalli non validi')
    unique={}
    for e in events:
        ident=e['event_id']
        if ident in unique:
            if unique[ident]!=e:raise ValueError('Evento duplicato con dati discordanti: '+ident)
            continue
        if e['end']<=e['start']:raise ValueError('Occupazione non positiva: '+ident)
        unique[ident]=dict(e)
    areas=defaultdict(list)
    for e in unique.values():
        if e['start']<end and e['end']>start:areas[e['area_id']].append(e)
    summary=[];segments=[];episodes=[];hourly=[];relations=[]
    for area,items in sorted(areas.items()):
        if cancel and cancel():raise InterruptedError('Annullato')
        arrivals=defaultdict(set);departures=defaultdict(set)
        for e in items:
            arrivals[max(start,e['start'])].add(e['event_id'])
            departures[min(end,e['end'])].add(e['event_id'])
        times=sorted({start,end}|set(arrivals)|set(departures));active=set();local=[]
        episode=None
        for a,b in zip(times,times[1:]):
            active.difference_update(departures[a]);active.update(arrivals[a]);n=len(active)
            if b<=a:continue
            excess=max(0,n-capacity) if capacity is not None else None
            sid=f'{area}:segment:{len(local)+1}'
            row={'area_id':area,'segment_id':sid,'start':a,'end':b,'seconds':b-a,'concurrent':n,'excess':excess,'event_ids':sorted(active)}
            local.append(row);segments.append(row)
            for ident in sorted(active):relations.append({'area_id':area,'segment_id':sid,'event_id':ident})
            if excess:
                if episode is None:episode={'area_id':area,'episode_id':f'{area}:episode:{len(episodes)+1}','start':a,'end':b,'seconds':b-a,'peak':n,'max_excess':excess,'excess_stall_seconds':excess*(b-a),'event_ids':set(active)}
                else:
                    episode['end']=b;episode['seconds']+=b-a;episode['peak']=max(episode['peak'],n);episode['max_excess']=max(episode['max_excess'],excess);episode['excess_stall_seconds']+=excess*(b-a);episode['event_ids'].update(active)
            elif episode is not None:
                episode['event_ids']=sorted(episode['event_ids']);episodes.append(episode);episode=None
        if episode is not None:episode['event_ids']=sorted(episode['event_ids']);episodes.append(episode)
        def metrics(lo,hi):
            relevant=[(s,max(0,min(hi,s['end'])-max(lo,s['start']))) for s in local if s['start']<hi and s['end']>lo]
            return {'area_id':area,'start':lo,'end':hi,'passages':sum(lo<=e['arrival']<hi for e in items),'capacity':capacity,'peak':max((s['concurrent'] for s,d in relevant),default=0),'overlap_seconds':sum(d for s,d in relevant if s['concurrent']>=2),'exceed_seconds':sum(d for s,d in relevant if s['excess']) if capacity is not None else None,'max_excess':max((s['excess'] for s,d in relevant),default=0) if capacity is not None else None,'excess_stall_seconds':sum(d*s['excess'] for s,d in relevant) if capacity is not None else None}
        total=metrics(start,end);total['episodes']=sum(e['area_id']==area for e in episodes) if capacity is not None else None;summary.append(total)
        lo=start
        while lo<end:
            hi=min(end,lo+bin_seconds);hourly.append(metrics(lo,hi));lo=hi
    return {'summary':summary,'segments':segments,'episodes':episodes,'bins':hourly,'relations':relations,'events':sorted((e for a in sorted(areas) for e in areas[a]),key=lambda e:(e['area_id'],e['arrival'],e['event_id']))}
