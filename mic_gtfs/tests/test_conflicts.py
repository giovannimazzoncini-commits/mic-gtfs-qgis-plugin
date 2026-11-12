import unittest,sys,types,importlib,datetime as dt
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PKG='_mic_gtfs_test_core'
package=types.ModuleType(PKG);package.__path__=[str(ROOT)];sys.modules[PKG]=package
core=importlib.import_module(PKG+'.conflicts');adapter=importlib.import_module(PKG+'.gtfs_adapter')

def event(i,a,b,area='S'):
    return {'event_id':i,'area_id':area,'arrival':a,'start':a,'end':b}

class CoreTests(unittest.TestCase):
    def test_touching_endpoints(self):
        r=core.analyse([event('a',0,10),event('b',10,20)],0,20,1);self.assertEqual(r['summary'][0]['peak'],1);self.assertEqual(r['episodes'],[])
    def test_simultaneous_capacity(self):
        r=core.analyse([event('a',0,20),event('b',0,20)],0,30,2);self.assertEqual(r['summary'][0]['overlap_seconds'],20);self.assertEqual(r['summary'][0]['exceed_seconds'],0)
    def test_excess_integral(self):
        r=core.analyse([event('a',0,30),event('b',0,30),event('c',0,30)],0,30,1);self.assertEqual(r['summary'][0]['excess_stall_seconds'],60)
    def test_continuous_episode_changes_members(self):
        r=core.analyse([event('a',0,30),event('b',0,10),event('c',10,30)],0,30,1);self.assertEqual(len(r['episodes']),1);self.assertEqual(r['episodes'][0]['seconds'],30)
    def test_duplicate(self):
        e=event('a',0,10);r=core.analyse([e,dict(e)],0,20,1);self.assertEqual(r['summary'][0]['passages'],1)
    def test_conflicting_duplicate(self):
        with self.assertRaises(ValueError):core.analyse([event('a',0,10),event('a',1,10)],0,20,1)
    def test_carry_in(self):
        r=core.analyse([event('a',-10,10)],0,20,1);self.assertEqual(r['summary'][0]['passages'],0);self.assertEqual(r['summary'][0]['peak'],1)
    def test_unknown_capacity(self):
        r=core.analyse([event('a',0,10),event('b',0,10)],0,20,None);self.assertIsNone(r['summary'][0]['exceed_seconds']);self.assertEqual(r['episodes'],[])
    def test_independent_areas(self):
        r=core.analyse([event('a',0,10,'A'),event('b',0,10,'B')],0,20,1);self.assertTrue(all(s['peak']==1 for s in r['summary']))
    def test_bin_boundary(self):
        r=core.analyse([event('a',9,11)],0,20,1,10);self.assertEqual([b['passages'] for b in r['bins']],[1,0]);self.assertEqual([b['peak'] for b in r['bins']],[1,1])
    def test_invalid_interval(self):
        with self.assertRaises(ValueError):core.analyse([event('a',10,0)],0,20)
    def test_cancel(self):
        with self.assertRaises(InterruptedError):core.analyse([event('a',0,10)],0,20,cancel=lambda:True)

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.cfg={'date':'2026-11-12','from':'08:00','to':'09:00','timezone':'Europe/Rome','stop_areas':{'S':'S'},'capacity':1,'dwell':45,'clearance':10,'use_departure':True,'bin_minutes':60}
        self.data={'rows':[{'trip_id':'T','stop_id':'S','stop_sequence':'1','arrival_time':'08:00:00','departure_time':'08:00:00'}],'trips':{'T':{'route_id':'R','service_id':'svc'}},'routes':{},'calendar':[],'calendar_dates':[{'service_id':'svc','date':'20261112','exception_type':'1'}]}
    def test_assumed_dwell(self):
        r=adapter.calculate(self.data,self.cfg);e=r['events'][0];self.assertEqual(e['end']-e['start'],55)
    def test_positive_departure(self):
        self.data['rows'][0]['departure_time']='08:02:00';r=adapter.calculate(self.data,self.cfg);self.assertEqual(r['events'][0]['end']-r['events'][0]['start'],130)
    def test_invalid_departure(self):
        self.data['rows'][0]['departure_time']='07:59:00';r=adapter.calculate(self.data,self.cfg);self.assertEqual(len(r['events']),0);self.assertEqual(len(r['diagnostics']),1)
    def test_calendar_removal(self):
        self.data['calendar_dates'][0]['exception_type']='2';r=adapter.calculate(self.data,self.cfg);self.assertEqual(r['summary'][0]['passages'],0);self.assertEqual(len(r['bins']),1)
    def test_previous_service_day_over_24(self):
        self.cfg.update({'from':'00:00','to':'01:00'});self.data['calendar_dates'][0]['date']='20261111';self.data['rows'][0].update(arrival_time='24:10:00',departure_time='24:10:00');r=adapter.calculate(self.data,self.cfg);self.assertEqual(r['summary'][0]['passages'],1);self.assertEqual(r['events'][0]['service_date'],'2026-11-11')
    def test_midnight_carry_in(self):
        self.cfg.update({'from':'00:00','to':'01:00','dwell':120});self.data['calendar_dates'][0]['date']='20261111';self.data['rows'][0].update(arrival_time='23:59:30',departure_time='23:59:30');r=adapter.calculate(self.data,self.cfg);self.assertEqual(r['summary'][0]['passages'],0);self.assertEqual(r['summary'][0]['peak'],1)
    def test_frequency_rejected(self):
        self.data['frequencies']=[{'trip_id':'T'}]
        with self.assertRaises(ValueError):adapter.calculate(self.data,self.cfg)
    def test_missing_arrival_diagnostic(self):
        self.data['rows'][0]['arrival_time']='';r=adapter.calculate(self.data,self.cfg);self.assertEqual(r['summary'][0]['status'],'incompleto: verificare diagnostica')
    def test_dst_ambiguous_boundary(self):
        tz=adapter.ZoneInfo('Europe/Rome')
        with self.assertRaises(ValueError):adapter.local_instant(dt.date(2026,10,25),'02:30',tz)
    def test_full_day(self):
        self.cfg.update({'from':'00:00','to':'00:00'});r=adapter.calculate(self.data,self.cfg);self.assertEqual(r['window']['end']-r['window']['start'],86400)
    def test_same_trip_repeated_stop(self):
        r=dict(self.data['rows'][0]);r['stop_sequence']='5';r['arrival_time']='08:10:00';r['departure_time']='08:10:00';self.data['rows'].append(r);self.assertEqual(adapter.calculate(self.data,self.cfg)['summary'][0]['passages'],2)

if __name__=='__main__':unittest.main()
