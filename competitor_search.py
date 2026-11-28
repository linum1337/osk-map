"""Unicode-aware product fragment search and safe text highlight positions."""
import re,unicodedata
_VISUAL=str.maketrans('авекмнорстух','abekmhopctyx')
_ALIASES={'osk':'оск','nag':'наг','lanset':'лансет','kn':'кн','ов':'волок','волокно':'волок','волокна':'волок','волокон':'волок','волоконный':'волок','оптика':'опти','оптический':'опти','оптическая':'опти','оптические':'опти','оптического':'опти'}
_ENDINGS=('иями','ями','ами','ого','ему','ыми','ими','ий','ый','ая','ое','ые','ой','ов','ев','ом','ем','ах','ях','ы','и','а','я','у','ю','е','о')
def normalized_map(value):
 text=str(value or '');out=[];positions=[]
 for match in re.finditer(r'[^\W_]+',text,re.UNICODE):
  raw=match.group();word=unicodedata.normalize('NFKC',raw).casefold().replace('ё','е')
  alias=_ALIASES.get(word)
  if alias:word=alias
  elif len(word)>=5 and re.fullmatch('[а-я]+',word):
   for suffix in _ENDINGS:
    if word.endswith(suffix) and len(word)-len(suffix)>=3:word=word[:-len(suffix)];break
  word=word.translate(_VISUAL)
  if out:out.append(' ');positions.append((match.start(),match.start()))
  out.extend(word)
  if alias:positions.extend([(match.start(),match.end())]*len(word))
  else:positions.extend([(match.start()+min(i,len(raw)-1),match.start()+min(i+1,len(raw))) for i in range(len(word))])
 return ''.join(out),positions
def normalize(value):return normalized_map(value)[0]
_STOP={normalize(w) for w in ['и','с','со','для','на','в','по','из']}
def terms(query):return list(dict.fromkeys(w for w in normalize(query).split() if w not in _STOP))[:16]
def fields(record,provider=''):
 values=[('name','Товар',record.get('name','')),('sku','Артикул',record.get('sku','')),('provider','Поставщик',provider),('manufacturer','Производитель',record.get('manufacturer','')),('brand','Бренд',record.get('brand','')),('originCountry','Страна по данным поставщика',record.get('originCountry','')),('category','Категория',record.get('category','')),('categoryPath','Раздел каталога',record.get('categoryPath','')),('availability','Наличие',record.get('availability','')),('description','Описание',record.get('description',''))]
 for key,value in (record.get('properties') or {}).items():values.append(('property:'+str(key),'Характеристика',str(key)+': '+str(value)))
 for i,price in enumerate(record.get('prices') or []):
  values.append(('offer:'+str(i),'Исполнение', ' · '.join(str(price.get(k,'')) for k in ['label','sku','condition','availability'] if price.get(k))))
 return [(key,label,str(value)) for key,label,value in values if value]
def document(record,provider=''):
 values=[v for _,_,v in fields(record,provider)];compact=[]
 for value in values:
  for token in re.findall(r'[^\W_]+(?:[-/.,][^\W_]+)+',value,re.UNICODE):compact.append(normalize(token).replace(' ',''))
 sku=normalize(record.get('sku',''))
 if sku:compact.append(sku.replace(' ',''))
 return normalize(' '.join(values))+' '+' '.join(compact),normalize(record.get('name','')),sku
def ranges(value,words):
 normalized,mapping=normalized_map(value);found=[]
 for word in words:
  start=0
  while word and (at:=normalized.find(word,start))>=0:
   found.append((mapping[at][0],mapping[at+len(word)-1][1]));start=at+len(word)
 if words:
  compact=''.join(ch for ch in normalized if ch!=' ');locations=[pos for ch,pos in zip(normalized,mapping) if ch!=' ']
  for word in words:
   if word in normalized:continue
   start=0
   while word and (at:=compact.find(word,start))>=0:
    found.append((locations[at][0],locations[at+len(word)-1][1]));start=at+len(word)
 merged=[]
 for lo,hi in sorted(found):
  if merged and lo<=merged[-1][1]:merged[-1][1]=max(hi,merged[-1][1])
  elif hi>lo:merged.append([lo,hi])
 return merged
def highlights(record,words,provider=''):
 result=[]
 for key,label,value in fields(record,provider):
  spans=ranges(value,words)
  if spans:result.append({'key':key,'label':label,'text':value,'ranges':spans})
 return result
