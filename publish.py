"""Publish small daily JSON files."""
import json, sys
from pathlib import Path
from datetime import date
base=Path(__file__).resolve().parent
j=json.loads((base/'schedule.json').read_text())
assert j['v']==1 and j['uics']==['87444000','87444265']
assert len(j['jours'])>=2 and any(j['jours'].values())
outputs = {}
for day,trips in j['jours'].items():
    assert date.fromisoformat(day).isoformat()==day
    assert len(trips)<=80
    for t in trips:
        assert isinstance(t['n'],str) and 0<=t['d']<86400 and 0<t['a']-t['d']<=10800
    payload={k:j[k] for k in ('v','source','source_url','genere_le','uics')}
    payload.update(jour=day,trains=trips)
    s=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
    assert len(s.encode())<3900, 'Fichier journalier trop grand pour le cache ESP32'
    outputs[day] = s
(base/'data').mkdir(exist_ok=True)
for day, s in outputs.items():
    (base/'data'/f'{day}.json').write_text(s,encoding='utf-8')
for p in (base/'data').glob('*.json'):
    if p.stem not in j['jours']: p.unlink()
print(f'{len(j["jours"])} fichiers journaliers prêts')
