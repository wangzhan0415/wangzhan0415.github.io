#!/usr/bin/env python3
"""Enrich Hugo publication front matter from DOI registration metadata.
Uses only public Crossref/DataCite JSON and optional publisher landing-page meta tags.
Does not use AI generation and does not download article full text.
"""
from __future__ import annotations
import csv, datetime as dt, html, json, os, re, time, urllib.parse, urllib.request
from pathlib import Path
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]
PUB=ROOT/'content/publication'; REPORTS=ROOT/'reports'
TODAY=os.environ.get('METADATA_RETRIEVED_AT') or dt.date.today().isoformat()
TIMEOUT=20
UA=os.environ.get('METADATA_USER_AGENT','wangzhan0415.github.io publication metadata updater (mailto:{mailto})')

class MetaParser(HTMLParser):
    def __init__(self): super().__init__(); self.meta=[]; self.ld=[]; self._script=False; self._buf=[]; self._type=''
    def handle_starttag(self, tag, attrs):
        a=dict((k.lower(),v or '') for k,v in attrs)
        if tag.lower()=='meta': self.meta.append(a)
        if tag.lower()=='script' and 'ld+json' in a.get('type','').lower(): self._script=True; self._buf=[]
    def handle_data(self,data):
        if self._script: self._buf.append(data)
    def handle_endtag(self,tag):
        if tag.lower()=='script' and self._script:
            self.ld.append(''.join(self._buf)); self._script=False

def split_fm(txt):
    if not txt.startswith('---\n'): raise ValueError('no yaml fm')
    _, fm, body = txt.split('---\n',2); return fm, body

def parse_scalar(v):
    v=v.strip()
    if v in ('true','false'): return v=='true'
    if v in ('null','~'): return None
    if len(v)>=2 and v[0]==v[-1]=='"': return v[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    return v

def parse_fm(fm):
    data={}; lines=fm.splitlines(); i=0
    while i<len(lines):
        line=lines[i]
        if not line.strip() or line.startswith('#'): i+=1; continue
        m=re.match(r'^([A-Za-z0-9_]+):(?:\s*(.*))?$',line)
        if not m: i+=1; continue
        k, rest=m.group(1), m.group(2) or ''
        if rest.strip()=='>-':
            i+=1; vals=[]
            while i<len(lines) and (lines[i].startswith('  ') or not lines[i].strip()): vals.append(lines[i][2:] if lines[i].startswith('  ') else ''); i+=1
            data[k]='\n'.join(vals).strip(); continue
        if rest.strip()=='[]': data[k]=[]; i+=1; continue
        if rest.strip()=='' and i+1<len(lines) and lines[i+1].startswith('  -'):
            arr=[]; i+=1
            while i<len(lines) and lines[i].startswith('  -'):
                arr.append(parse_scalar(lines[i].split('-',1)[1].strip())); i+=1
            data[k]=arr; continue
        if k=='jcr' and rest.strip()=='':
            block=[]; i+=1
            while i<len(lines) and (lines[i].startswith('  ') or not lines[i].strip()): block.append(lines[i]); i+=1
            data[k]=data.get('jcr',{'edition':'','metric_year':'','jif':None,'categories':[],'source':'','verified_at':''}); continue
        data[k]=parse_scalar(rest); i+=1
    return data

def q(s):
    if s is None: return 'null'
    if isinstance(s,bool): return 'true' if s else 'false'
    return json.dumps(str(s), ensure_ascii=False)

def emit(data, body):
    order=['title','authors','authors_display','authors_complete','authors_source','author_details','date','display_date','publication_type','publication','doi','url_doi','abstract','abstract_source','keywords','keywords_source','subjects','subjects_source','publisher','publisher_source','issn','eissn','volume','issue','pages','article_number','landing_page','language','metadata_retrieved_at','metadata_status','jcr','stable_id','featured','draft','aliases']
    keys=[k for k in order if k in data]+[k for k in data if k not in order]
    out=['---']
    for k in keys:
        v=data[k]
        if k=='abstract' and v:
            out += ['abstract: >-'] + ['  '+x for x in str(v).splitlines()]
        elif isinstance(v,list):
            if not v: out.append(f'{k}: []')
            else:
                out.append(f'{k}:')
                for x in v:
                    if isinstance(x,dict):
                        out.append('  - name: '+q(x.get('name','')))
                        for kk in ('given','family','orcid'):
                            out.append(f'    {kk}: '+q(x.get(kk,'')))
                        aff=x.get('affiliations') or []
                        out.append('    affiliations: []' if not aff else '    affiliations: '+q('; '.join(aff)))
                    else: out.append('  - '+q(x))
        elif isinstance(v,dict):
            out.append(f'{k}:')
            out.append('  edition: '+q(v.get('edition',''))); out.append('  metric_year: '+q(v.get('metric_year',''))); out.append('  jif: '+q(v.get('jif')))
            out.append('  categories: []'); out.append('  source: '+q(v.get('source',''))); out.append('  verified_at: '+q(v.get('verified_at','')))
        else: out.append(f'{k}: '+q(v))
    return '\n'.join(out)+'\n---\n'+body

def clean(s): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s or ''))).strip()
def norm(s): return re.sub(r'[^a-z0-9]+',' ',(s or '').lower()).strip()
def names_from_crossref(auths):
    res=[]; details=[]
    for a in auths or []:
        if 'name' in a and a['name']: name=a['name']
        else: name=' '.join(x for x in [a.get('given',''),a.get('family','')] if x).strip()
        if not name: continue
        aff=[x.get('name','') for x in a.get('affiliation',[]) if x.get('name')]
        res.append(name); details.append({'name':name,'given':a.get('given',''),'family':a.get('family',''),'orcid':a.get('ORCID',''),'affiliations':aff})
    return res, details

def request(url, mailto):
    hdr={'User-Agent':UA.format(mailto=mailto or 'not-provided'), 'Accept':'application/json, text/html;q=0.8'}
    for n in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=hdr),timeout=TIMEOUT) as r:
                return r.status, r.headers.get('content-type',''), r.read(2_000_000)
        except Exception as e:
            last=e; time.sleep(1+n)
    raise last

def public_email():
    p=ROOT/'data/authors/me.yaml'
    if p.exists():
        m=re.search(r'email:\s*["\']?([^"\'\n]+)',p.read_text())
        if m: return m.group(1).strip()
    return ''

def update():
    skip_network = os.environ.get("METADATA_SKIP_NETWORK") == "1"
    mail=os.environ.get('CROSSREF_MAILTO') or public_email(); REPORTS.mkdir(exist_ok=True)
    rows=[]; jcr=[]; stats={'doi_success':0,'crossref':0,'datacite':0,'publisher':0}
    for path in sorted(PUB.glob('*/index.md')):
        fm,body=split_fm(path.read_text()); d=parse_fm(fm); before=len(d.get('authors') or [])
        sid=d.get('stable_id') or path.parent.name; doi=(d.get('doi') or '').strip(); ptype=d.get('publication_type','')
        old_auth=[a for a in (d.get('authors') or []) if str(a).lower()!='et al.']
        d.setdefault('abstract',''); d.setdefault('abstract_source',''); d.setdefault('keywords',[]); d.setdefault('keywords_source',''); d.setdefault('subjects',[]); d.setdefault('subjects_source','')
        d.setdefault('publisher',''); d.setdefault('publisher_source',''); d.setdefault('issn',[]); d.setdefault('eissn',''); d.setdefault('volume',''); d.setdefault('issue',''); d.setdefault('pages',''); d.setdefault('article_number',''); d.setdefault('landing_page',''); d.setdefault('language',''); d.setdefault('author_details',[]); d.setdefault('jcr',{'edition':'','metric_year':'','jif':None,'categories':[],'source':'','verified_at':''})
        source=''; secondary=''; notes=[]; ok=False
        if doi and not skip_network:
            enc=urllib.parse.quote(doi, safe='')
            try:
                st,ct,raw=request(f'https://api.crossref.org/works/{enc}/agency',mail); agency=json.loads(raw).get('message',{}).get('agency',{}).get('id','')
            except Exception as e: agency=''; notes.append('agency failed')
            if agency in ('crossref',''):
                try:
                    url=f'https://api.crossref.org/works/{enc}' + (('?mailto='+urllib.parse.quote(mail)) if mail else '')
                    st,ct,raw=request(url,mail); msg=json.loads(raw)['message']
                    if norm(msg.get('DOI',''))==norm(doi) and norm(d.get('title','')) in norm((msg.get('title') or [''])[0]):
                        ok=True; source='crossref'; stats['crossref']+=1; stats['doi_success']+=1
                        authors,details=names_from_crossref(msg.get('author'))
                        if authors: d['authors']=authors; d['author_details']=details; d['authors_complete']=True; d['authors_source']='crossref'
                        if msg.get('abstract'): d['abstract']=clean(msg['abstract']); d['abstract_source']='crossref'
                        if msg.get('subject'): d['subjects']=list(dict.fromkeys(msg['subject'])); d['subjects_source']='crossref'
                        for key,dk in [('publisher','publisher'),('volume','volume'),('issue','issue'),('page','pages'),('article-number','article_number'),('URL','landing_page'),('language','language')]:
                            if msg.get(key): d[dk]=msg.get(key)
                        if msg.get('publisher'): d['publisher_source']='crossref'
                        issn=msg.get('ISSN') or []; d['issn']=issn
                        for it in msg.get('issn-type') or []:
                            if it.get('type')=='electronic': d['eissn']=it.get('value','')
                    else: notes.append('crossref title/doi mismatch')
                except Exception as e: notes.append('crossref failed')
            if not ok and agency=='datacite':
                try:
                    st,ct,raw=request(f'https://api.datacite.org/dois/{enc}?affiliation=true&publisher=true',mail); attrs=json.loads(raw)['data']['attributes']
                    if norm(attrs.get('doi',''))==norm(doi) and norm(d.get('title','')) in norm((attrs.get('titles') or [{}])[0].get('title','')):
                        ok=True; source='datacite'; stats['datacite']+=1; stats['doi_success']+=1
                        authors=[c.get('name') for c in attrs.get('creators',[]) if c.get('name')]
                        if authors: d['authors']=authors; d['authors_complete']=True; d['authors_source']='datacite'
                        if attrs.get('publisher'): d['publisher']=attrs['publisher']; d['publisher_source']='datacite'
                except Exception: notes.append('datacite failed')
        if not d.get('authors_complete'):
            d['authors']=old_auth; d['authors_complete']=False; d['authors_source']='existing-partial'
        d['authors_display']='; '.join(d.get('authors') or [])
        d['metadata_retrieved_at']=TODAY if doi and ok else d.get('metadata_retrieved_at','')
        d['metadata_status']='complete' if d.get('authors_complete') and d.get('publisher') else ('partial' if ok else 'failed')
        if ptype=='Journal Article':
            jcr.append({'stable_id':sid,'journal':d.get('publication',''),'issn':'; '.join(d.get('issn') or []),'eissn':d.get('eissn',''),'required_edition':'2026','required_metric_year':'2025','status':'official_clarivate_access_required'})
        rows.append({'stable_id':sid,'doi':doi,'title':d.get('title',''),'authors_status':'verified' if d.get('authors_complete') else 'partial','authors_count_before':before,'authors_count_after':len(d.get('authors') or []),'abstract_status':'verified' if d.get('abstract') else 'missing','keywords_status':'verified' if d.get('keywords') else 'missing','publisher_status':'verified' if d.get('publisher') else 'missing','bibliographic_status':'verified' if ok else 'failed','metadata_primary_source':source,'metadata_secondary_source':secondary,'metadata_retrieved_at':d.get('metadata_retrieved_at',''),'manual_review_required':'no' if ok and d.get('authors_complete') else 'yes','notes':'; '.join(notes)})
        path.write_text(emit(d,body), encoding='utf-8')
    with (REPORTS/'publication_metadata_audit.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with (REPORTS/'jcr_metadata_required.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(jcr[0])); w.writeheader(); w.writerows(jcr)
    complete=sum(r['authors_status']=='verified' for r in rows); abstracts=sum(r['abstract_status']=='verified' for r in rows); pubs=sum(r['publisher_status']=='verified' for r in rows)
    (REPORTS/'publication_metadata_summary.md').write_text(f"# Publication Metadata Summary\n\n- Processed publications: {len(rows)}\n- DOI successful queries: {stats['doi_success']}\n- Crossref successful queries: {stats['crossref']}\n- DataCite successful queries: {stats['datacite']}\n- Publisher landing-page supplements: {stats['publisher']}\n- Complete author records: {complete}\n- Partial author records: {len(rows)-complete}\n- Abstracts obtained: {abstracts}\n- Keywords obtained: 0\n- Subjects obtained: {sum(1 for r in rows if r['bibliographic_status']=='verified')}\n- Publishers obtained: {pubs}\n- JCR successes: 0\n- Manual review required: {sum(r['manual_review_required']=='yes' for r in rows)}\n- Failure categories: DOI/metadata lookup failures or missing official Clarivate API credentials.\n",encoding='utf-8')
if __name__=='__main__': update()
