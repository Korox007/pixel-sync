"""Pixel Sync : collecte Open-Meteo et export JSON. Python 3.9+, sans dépendance."""
import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Paris')
VILLES = {'Caen': (49.1829, -0.3707), 'Lisieux': (49.1450, 0.2250)}
PERIODES = {'matin': (6,12), 'journee': (12,18), 'soir': (18,24)}
GROUPES = {'soleil': {0}, 'eclaircies': {1,2}, 'couvert': {3},
           'brouillard': {45,48}, 'pluie': {51,53,55,56,57,61,63,65,66,67},
           'neige': {71,73,75,77,85,86}, 'averses': {80,81,82}, 'orage': {95,96,99}}

def categorie(code):
    for nom, codes in GROUPES.items():
        if code in codes: return nom
    raise ValueError(f'Code météo inconnu : {code}')

def icone(nom, nuit=False):
    if nuit:
        return {'soleil':'nuit_degagee', 'eclaircies':'nuit_nuageuse',
                'couvert':'nuit_nuageuse', 'pluie':'nuit_pluvieuse',
                'averses':'nuit_pluvieuse'}.get(nom, nom)
    return nom

def arrondi(t):
    return int(t+0.5) if t>=0 else int(t-0.5)

def resume(tranches):
    if not tranches: raise ValueError('Période météo vide')
    categories = [categorie(x[1]) for x in tranches]
    comptes = Counter(categories)
    # Priorité aux événements significatifs, même s'ils sont brefs.
    if 'orage' in comptes: nom='orage'
    elif 'neige' in comptes: nom='neige'
    elif comptes['pluie'] + comptes['averses'] >= len(tranches)/2 and comptes['pluie'] >= comptes['averses']: nom='pluie'
    elif comptes['pluie'] or comptes['averses']: nom='averses' if comptes['averses'] or comptes['soleil'] or comptes['eclaircies'] else 'pluie'
    else:
        nom=max(comptes, key=lambda c:(comptes[c], ['soleil','eclaircies','couvert','brouillard'].index(c)))
    nuit=sum(x[2]==0 for x in tranches)>len(tranches)/2
    return {'icone':icone(nom,nuit),'min':arrondi(min(x[0] for x in tranches)),
            'max':arrondi(max(x[0] for x in tranches))}

def obtenir(lat, lon):
    params={'latitude':lat,'longitude':lon,'timezone':'Europe/Paris','forecast_days':3,
            'temperature_unit':'celsius','hourly':'temperature_2m,weather_code,is_day',
            'daily':'temperature_2m_min,temperature_2m_max,weather_code,sunrise,sunset',
            'current':'temperature_2m,weather_code,is_day'}
    url='https://api.open-meteo.com/v1/forecast?'+urlencode(params)
    with urlopen(url,timeout=25) as r: return json.load(r)

def traiter(d, jour):
    h=d['hourly']; jours=d['daily']; lendemain=(jour+timedelta(days=1)).isoformat()
    dates=[datetime.fromisoformat(x) for x in h['time']]
    periodes={}
    for nom,(debut,fin) in PERIODES.items():
        valeurs=[(t,c,n) for dt,t,c,n in zip(dates,h['temperature_2m'],h['weather_code'],h['is_day'])
                 if dt.date()==jour and debut<=dt.hour<fin]
        if len(valeurs)!=fin-debut or any(None in x for x in valeurs): raise ValueError('Données horaires incomplètes : '+nom)
        periodes[nom]=resume(valeurs)
    i=jours['time'].index(lendemain); j=jours['time'].index(jour.isoformat())
    periodes['demain']={'icone':icone(categorie(jours['weather_code'][i])),
                       'min':arrondi(jours['temperature_2m_min'][i]),'max':arrondi(jours['temperature_2m_max'][i])}
    c=d['current']; nom=categorie(c['weather_code'])
    return {'periodes':periodes,'actuel':{'heure':c['time'],'temperature':c['temperature_2m'],
            'code':c['weather_code'],'icone':icone(nom,c['is_day']==0),
            'precipitations':nom in {'pluie','averses','orage','neige'}},
            'lever':jours['sunrise'][j],'coucher':jours['sunset'][j]}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--sortie',type=Path,default=Path(__file__).with_name('meteo.json')); args=parser.parse_args()
    maintenant=datetime.now(ZONE); jour=maintenant.date()
    resultat={'v':1,'source':'Open-Meteo (CC BY 4.0)','source_url':'https://open-meteo.com/',
              'genere_le':maintenant.isoformat(timespec='seconds'),'jour':jour.isoformat(), 'villes':{}}
    for nom,(lat,lon) in VILLES.items(): resultat['villes'][nom]=traiter(obtenir(lat,lon),jour)
    if datetime.now(ZONE).date()!=jour: raise RuntimeError('Changement de date pendant la collecte ; relancer.')
    # Écriture atomique : conserve le dernier fichier valide si la récupération échoue.
    args.sortie.parent.mkdir(parents=True,exist_ok=True)
    tmp=args.sortie.with_suffix(args.sortie.suffix+'.tmp'); tmp.write_text(json.dumps(resultat,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8'); tmp.replace(args.sortie)
    print(args.sortie)

if __name__=='__main__': main()
