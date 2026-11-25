#!/usr/bin/env python3
"""Extract a pair of stops from a public GTFS feed. Python 3.9+, standard library only."""
import argparse, csv, io, json, re, sys, tempfile, urllib.request, zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import defaultdict
from zoneinfo import ZoneInfo

URL = 'https://eu.ftp.opendatasoft.com/sncf/plandata/Export_OpenData_SNCF_GTFS_NewTripId.zip'
SOURCE = 'SNCF Voyageurs — horaires GTFS, ODbL 1.0'
ZONE = ZoneInfo('Europe/Paris')
ORIGIN, DESTINATION = '87444000', '87444265'

def rows(z, name, optional=False):
    matches = [n for n in z.namelist() if n.rsplit('/', 1)[-1] == name]
    if not matches and optional: return
    if len(matches) != 1: raise ValueError('Fichier GTFS absent ou ambigu : '+name)
    with z.open(matches[0]) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig', newline=''))

def number(row):
    for value in [row.get('trip_short_name',''), row.get('trip_headsign','')]:
        m = re.fullmatch(r'\s*(?:TER\s+|NOMAD\s+)?(\d{3,8})\s*', value or '', re.I)
        if m: return m[1]
    m = re.match(r'^OCESN(\d+)[FR](?:\d|_|:|$)', row['trip_id'])
    return m[1] if m else None

def seconds(v):
    h,m,s = map(int,v.split(':'))
    if h<0 or not 0<=m<60 or not 0<=s<60: raise ValueError(v)
    return h*3600+m*60+s

def stop_code(v):
    for code in (ORIGIN,DESTINATION):
        if re.search(r'(?<!\d)'+code+r'(?!\d)', v): return code
    return None

def clock(s):
    return f'{s//3600:02d}:{s//60%60:02d}'

def gtfs_date(s): return date.fromisoformat(s[:4]+'-'+s[4:6]+'-'+s[6:8])

def extract(path, start, days=14):
    dates=[start+timedelta(days=i) for i in range(days)]
    with zipfile.ZipFile(path) as z:
        codes={}
        for row in rows(z,'stops.txt'):
            sid=row['stop_id']; code=stop_code(sid) or stop_code(row.get('parent_station','')) or stop_code(row.get('stop_code',''))
            if code: codes[sid]=code
        if set(codes.values())!={ORIGIN,DESTINATION}: raise ValueError('Les deux gares ne sont pas identifiées dans stops.txt')
        routes={r['route_id']:r['route_type'] for r in rows(z,'routes.txt')}
        valid_services=defaultdict(set); covered=set()
        weekday=('monday','tuesday','wednesday','thursday','friday','saturday','sunday')
        for r in rows(z,'calendar.txt',True):
            lo,hi=gtfs_date(r['start_date']),gtfs_date(r['end_date'])
            for d in dates:
                if lo<=d<=hi:
                    covered.add(d)
                    if r[weekday[d.weekday()]]=='1': valid_services[r['service_id']].add(d)
        for r in rows(z,'calendar_dates.txt',True):
            d=gtfs_date(r['date'])
            if d not in dates: continue
            covered.add(d)
            if r['exception_type']=='1': valid_services[r['service_id']].add(d)
            elif r['exception_type']=='2': valid_services[r['service_id']].discard(d)
        if not covered: raise ValueError('Aucune date demandée couverte par le GTFS')
        trips={}
        for r in rows(z,'trips.txt'):
            if not valid_services.get(r['service_id']): continue
            typ=routes.get(r['route_id'],'')
            # GTFS standard rail=2; extended railway service types 100..117.
            if not (typ=='2' or (typ.isdigit() and 100<=int(typ)<=117)): continue
            trips[r['trip_id']]=r
        stops=defaultdict(list)
        for r in rows(z,'stop_times.txt'):
            code=codes.get(r['stop_id'])
            if code and r['trip_id'] in trips:
                stops[r['trip_id']].append((int(r['stop_sequence']),code,r))
        result={d.isoformat():[] for d in dates if d in covered}
        unknown=set()
        for tid, ss in stops.items():
            ss.sort(key=lambda x:x[0]); trip=trips[tid]
            for seq, code, a in ss:
                if code!=ORIGIN or a.get('pickup_type','')=='1' or not a.get('departure_time'): continue
                # no railway service crossing midnight needed for this morning use
                dep=seconds(a['departure_time'])
                if not 0<=dep<86400: continue
                for seq2, code2, b in ss:
                    if seq2<=seq or code2!=DESTINATION or b.get('drop_off_type','')=='1' or not b.get('arrival_time'): continue
                    arr=seconds(b['arrival_time'])
                    if not 0<arr-dep<=3*3600: continue
                    n=number(trip)
                    if not n: unknown.add(tid)
                    for d in valid_services[trip['service_id']]:
                        result[d.isoformat()].append({'n':n or '', 'd':dep, 'a':arr})
                    break
        for day, rr in result.items():
            result[day]=[dict(n=n,d=d,a=a) for n,d,a in sorted({(r['n'],r['d'],r['a']) for r in rr},key=lambda x:(x[1],x[2],x[0]))]
        if not any(result.values()): raise ValueError('Aucun train direct trouvé : vérifier les identifiants / types du GTFS')
    return {'v':1,'source':SOURCE,'source_url':'https://transport.data.gouv.fr/datasets/horaires-sncf','genere_le':datetime.now(ZONE).isoformat(timespec='seconds'),'du':min(result),'au':max(result),'uics':[ORIGIN,DESTINATION],'jours':result,'numeros_non_identifies':len(unknown)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--zip',type=Path,help='archive officielle déjà téléchargée');p.add_argument('--date',type=date.fromisoformat,default=datetime.now(ZONE).date());p.add_argument('--jours',type=int,default=14);p.add_argument('--sortie',type=Path,default=Path('schedule.json')); args=p.parse_args()
    if not 1<=args.jours<=30: p.error('--jours : 1 à 30')
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path=args.zip
            if path is None:
                path=Path(tmp)/'sncf.zip';print('Téléchargement du GTFS officiel SNCF...',flush=True)
                req=urllib.request.Request(URL,headers={'User-Agent':'Pixel-Sync/1.0'})
                with urllib.request.urlopen(req,timeout=60) as r,path.open('wb') as f:
                    import shutil;shutil.copyfileobj(r,f)
            print('Extraction des trains directs...',flush=True)
            data=extract(path,args.date,args.jours)
        required = {args.date.isoformat(), (args.date + timedelta(days=1)).isoformat()} if args.jours >= 2 else {args.date.isoformat()}
        if not required.issubset(data['jours']): raise ValueError('Feed does not cover the requested immediate dates')
        args.sortie.parent.mkdir(parents=True,exist_ok=True)
        out=args.sortie.with_suffix('.tmp');out.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8');out.replace(args.sortie)
        print(f"{len(data['jours'])} days extracted")
        print('\nFichier :',args.sortie.resolve()); print('Numéros non identifiés :',data['numeros_non_identifies'])
    except Exception as e: print('ERREUR :',e,file=sys.stderr);sys.exit(1)
if __name__=='__main__': main()
