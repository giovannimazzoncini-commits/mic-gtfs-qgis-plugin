import collections,math

def seconds(s):
 try:
  h,m,x=map(int,s.split(':'));return h*3600+m*60+x
 except (ValueError,AttributeError):return None

def active(data,day):
 key=day.strftime('%Y%m%d');w=['monday','tuesday','wednesday','thursday','friday','saturday','sunday'][day.weekday()]
 services={r['service_id'] for r in data.get('calendar',[]) if r.get('start_date','')<=key<=r.get('end_date','') and r.get(w)=='1'}
 for r in data.get('calendar_dates',[]):
  if r['date']==key:
   if r['exception_type']=='1':services.add(r['service_id'])
   elif r['exception_type']=='2':services.discard(r['service_id'])
 return {r['trip_id'] for r in data['trips'] if r.get('service_id') in services}

def search(sequences,tids,origin,limit,changes,buffer,reverse,saving,tick):
 oriented={};boarding=collections.defaultdict(list);direct=collections.defaultdict(list)
 for tid in sorted(tids):
  rows=[]
  for i,r in enumerate(sequences.get(tid,[])):
   a,b=seconds(r.get('arrival_time','')),seconds(r.get('departure_time',''))
   if a is None or b is None:continue
   p=(r.get('pickup_type','') or '0')=='0';d=(r.get('drop_off_type','') or '0')=='0'
   rows.append((i,r['stop_id'],-b if reverse else a,-a if reverse else b,d if reverse else p,p if reverse else d))
  oriented[tid]=list(reversed(rows)) if reverse else rows
 for tid,seq in oriented.items():
  for pos,x in enumerate(seq):
   if x[4]:boarding[x[1]].append((x[3],tid,pos))
   if x[1]==origin and x[4]:
    for y in seq[pos+1:]:
     if y[5] and y[2]>=x[3]:direct[y[1]].append((x[3],y[2],[(tid,x[0],y[0])]))
 for opts in boarding.values():opts.sort()
 candidates=collections.defaultdict(list)
 for sid,opts in direct.items():
  for start,end,legs in opts:
   if 0<=end-start<=limit:candidates[sid].append((start,end,legs))
 if changes:
  for n,(tid,seq) in enumerate(oriented.items()):
   for pos,x in enumerate(seq):
    if x[1]!=origin or not x[4]:continue
    start=x[3]
    for y in seq[pos+1:]:
     if not y[5] or not 0<=y[2]-start<=limit:continue
     for departure,t2,p2 in boarding.get(y[1],[]):
      if departure<y[2]+buffer:continue
      if departure>start+limit:break
      if t2==tid:continue
      z=oriented[t2][p2]
      for end in oriented[t2][p2+1:]:
       if not end[5] or end[1]==origin or not 0<=end[2]-start<=limit:continue
       if any(ds>=start and de<=end[2]+saving for ds,de,dl in direct.get(end[1],[])):continue
       candidates[end[1]].append((start,end[2],[(tid,x[0],y[0]),(t2,z[0],end[0])]))
   if n%10==0:tick()
 kept=[]
 for sid,opts in candidates.items():
  if sid==origin:continue
  frontier=[]
  for start,end,legs in sorted(opts,key=lambda c:(-c[0],c[1],len(c[2]))):
   if any(s>=start and e<=end and len(ls)<=len(legs) for s,e,ls in frontier):continue
   frontier=[c for c in frontier if not(start>=c[0] and end<=c[1] and len(legs)<=len(c[2]))];frontier.append((start,end,legs))
  for start,end,legs in frontier:kept.append((sid,end-start,[(t,j,i) for t,i,j in reversed(legs)] if reverse else legs))
 return kept

def connection(legs,trips,sequences):
 return tuple(trips[t]['route_id'] for t,i,j in legs),sequences[legs[1][0]][legs[1][1]]['stop_id'] if len(legs)>1 else ''

def project_ordered(poly,stops,tolerance,tick):
 if len(poly)<2 or len(stops)<2:raise ValueError('Shape o sequenza insufficienti')
 sx=111320*math.cos(math.radians(sum(y for x,y in poly)/len(poly)));sy=111320;xy=[(x*sx,y*sy) for x,y in poly];cum=[0.0]
 for a,b in zip(xy,xy[1:]):cum.append(cum[-1]+math.hypot(b[0]-a[0],b[1]-a[1]))
 candidates=[]
 for n,(lon,lat) in enumerate(stops):
  x,y=lon*sx,lat*sy;unique={}
  for k,(a,b) in enumerate(zip(xy,xy[1:])):
   dx,dy=b[0]-a[0],b[1]-a[1];den=dx*dx+dy*dy
   if not den:continue
   t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/den));err=math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)
   if err<=tolerance:
    p=cum[k]+t*math.sqrt(den);key=round(p,3)
    if key not in unique or err*err<unique[key][1]:unique[key]=p,err*err
  if not unique:raise ValueError('Fermata fuori tolleranza: indice '+str(n))
  candidates.append(sorted(unique.values()))
  if n%20==0:tick()
 costs=[c for p,c in candidates[0]];parents=[None]
 for row in range(1,len(candidates)):
  new=[];links=[];j=0;best=(float('inf'),None)
  for p,c in candidates[row]:
   while j<len(candidates[row-1]) and candidates[row-1][j][0]<=p+0.001:
    if costs[j]<best[0]:best=costs[j],j
    j+=1
   new.append(c+best[0]);links.append(best[1])
  costs=new;parents.append(links)
 index=min(range(len(costs)),key=costs.__getitem__)
 if not math.isfinite(costs[index]):raise ValueError('Proiezione monotona impossibile')
 positions=[0.0]*len(stops)
 for row in range(len(stops)-1,-1,-1):
  positions[row]=candidates[row][index][0]
  if row:index=parents[row][index]
 if positions[-1]-positions[0]<0.01:raise ValueError('Associazione degenerata')
 return cum,positions

def clip(poly,cum,a,b):
 if b<=a or a<cum[0]-0.001 or b>cum[-1]+0.001:raise ValueError('Intervallo non valido')
 def point(d):
  for k in range(len(cum)-1):
   if cum[k]<=d<=cum[k+1] and cum[k+1]>cum[k]:
    f=(d-cum[k])/(cum[k+1]-cum[k]);return poly[k][0]+f*(poly[k+1][0]-poly[k][0]),poly[k][1]+f*(poly[k+1][1]-poly[k][1])
  raise ValueError('Interpolazione impossibile')
 return [point(a)]+[p for p,d in zip(poly,cum) if a<d<b]+[point(b)]
