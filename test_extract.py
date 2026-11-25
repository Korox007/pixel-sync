import io, zipfile, tempfile, unittest, csv
from pathlib import Path
from datetime import date
from extract import extract, number

def table(z,name,headers,rows):
    f=io.StringIO(); w=csv.writer(f);w.writerow(headers);w.writerows(rows);z.writestr(name+'.txt',f.getvalue())

def fixture(path):
    with zipfile.ZipFile(path,'w') as z:
        table(z,'stops',['stop_id','stop_name'],[('StopPoint:OCETrain TER-87444000','Alpha'),('StopPoint:OCETrain TER-87444265','Beta'),('StopPoint:OCETrain TER-87384008','Gamma')])
        table(z,'routes',['route_id','route_type'],[('rail','2'),('bus','3')])
        table(z,'calendar',['service_id','monday','tuesday','wednesday','thursday','friday','saturday','sunday','start_date','end_date'],[['week',1,1,1,1,1,0,0,'20261125','20261208'],['sat',0,0,0,0,0,1,0,'20261125','20261208']])
        table(z,'calendar_dates',['service_id','date','exception_type'],[['week','20261127',2],['add','20261127',1]])
        trips=[];st=[];ca='StopPoint:OCETrain TER-87444000';li='StopPoint:OCETrain TER-87444265';pa='StopPoint:OCETrain TER-87384008'
        def add(num,srv,dep,arr,route='rail',order=(ca,li),drop='0',suffix=''):
            tid=f'OCESN{num}F1187_F:TER:FR:{srv}{suffix}'; trips.append([route,srv,tid,'Gamma'])
            for i,(stop,time) in enumerate(zip(order,[dep,arr])): st.append([tid,time,time,stop,i+1,'0',drop if i==1 else '0'])
        add('710001','week','07:11:00','07:39:00');add('710002','week','07:43:00','08:05:00');add('710003','week','09:12:00','09:40:00')
        add('710004','week','09:04:00','10:45:00',order=(ca,pa));add('710005','week','08:24:00','08:52:00',order=(li,ca));add('123456','week','08:23:00','08:50:00',route='bus');add('1111','week','08:25:00','08:50:00',drop='1')
        add('710002','sat','09:17:00','09:39:00');add('710001','add','07:11:00','07:39:00');add('710003','add','09:12:00','09:40:00');add('710006','add','08:23:00','08:45:00')
        table(z,'trips',['route_id','service_id','trip_id','trip_headsign'],trips)
        table(z,'stop_times',['trip_id','arrival_time','departure_time','stop_id','stop_sequence','pickup_type','drop_off_type'],st)
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();p=Path(self.tmp.name)/'test.zip';fixture(p);self.data=extract(p,date(2026,11,25),14)
    def tearDown(self): self.tmp.cleanup()
    def test_route(self): self.assertEqual([r['n'] for r in self.data['jours']['2026-11-26']],['710001','710002','710003'])
    def test_exception(self): self.assertEqual([r['n'] for r in self.data['jours']['2026-11-27']],['710001','710006','710003'])
    def test_shift(self): self.assertEqual(self.data['jours']['2026-11-28'][0]['d'],9*3600+17*60)
    def test_empty_day(self): self.assertEqual(self.data['jours']['2026-11-29'],[])
    def test_number(self): self.assertEqual(number({'trip_id':'OCESN710002F1187_F:TER:FR:Line:','trip_headsign':'Gamma'}),'710002')
if __name__=='__main__': unittest.main(verbosity=2)
