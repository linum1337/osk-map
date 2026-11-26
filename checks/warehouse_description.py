"""Summary descriptions use source marking and known catalogue shape, never construction."""
from pathlib import Path
import sys,copy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import warehouse_prices as prices
rows=[dict(construction='ОКПД-8А-(3,0)-1/5,8',rod='1.6 ROD',type='круглый',pricePerKm='10000',sourceRow=1),dict(construction='ОКПД-1А-(1,0)-1/4,2',rod='1.0 ROD',type='круглый',pricePerKm='5000',sourceRow=2)]
assert prices.short_descriptions(['ОКПД-8А-(3,0)-1/5,6 Ультракабель'],'1,6 ROD',rows)==['Круглый, 8 волокон, 3 кН']
assert prices.short_descriptions(['ОКПД-1А-(1,0)-1/4,2','ОКПД-1А-(1,5)-1/4,2 СК'],'1,0 ROD',rows)==['Круглый, 1 волокно, 1 кН','Круглый, 1 волокно, 1,5 кН']
for count,word in [(2,'волокна'),(5,'волокон'),(11,'волокон'),(21,'волокно'),(24,'волокна')]:assert prices.short_descriptions([f'ОКПД-{count}А-(3,0)-1/5,6'],'1.6 ROD',rows)==[f'{count} {word}, 3 кН']
assert prices.short_descriptions(['ДРУГОЙ-8А-(3,0)'],'1.6 ROD',rows)==['8 волокон']
assert prices.short_descriptions([], '1.6 ROD',rows)==[]
cat=dict(rows=rows,version='fixture',title='Fixture')
snapshot={'items':[],'groups':[dict(key='fixture',construction='ОКПД-4А-(1,5)-1/4,8',markings=['ОКПД-8А-(3,0)-1/5,6'],rod='1.6 ROD')]}
hidden=prices.decorate(copy.deepcopy(snapshot),{'role':'warehouse','login':'fixture'},cat)
assert hidden['groups'][0]['descriptions']==['Круглый, 8 волокон, 3 кН']
assert 'priceVersion' not in hidden and 'prices' not in hidden['groups'][0]
changed=copy.deepcopy(cat);changed['rows'][0]['pricePerKm']='12345'
assert prices.decorate(copy.deepcopy(snapshot),{'role':'warehouse','login':'fixture'},changed)['descriptionVersion']==hidden['descriptionVersion']
print('PASS: markings before construction, fibre grammar, loads, known shape, multiple variants, no invented shape, no price leak or monetary metadata in description version')
