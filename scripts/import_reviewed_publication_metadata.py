#!/usr/bin/env python3
import argparse, hashlib, json, os, re, sys, tempfile, unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

EXPECTED={"publications":49,"journal_articles":18,"conference_papers":31,"with_keywords":43,"without_keywords":6}
IMMUTABLE=["stable_id","title","date","display_date","display_year","display_month","publication_type","publication","doi","url_doi","featured","draft"]
TARGET=["authors","authors_display","authors_complete","authors_source","abstract","abstract_source","keywords","keywords_source","keywords_status","metadata_status","metadata_retrieved_at"]

class Fail(Exception): pass

def q(s): return '"'+str(s).replace('\\','\\\\').replace('"','\\"')+'"'
def arr(name, vals):
    if not vals: return [f"{name}: []"]
    return [f"{name}:"]+[f"  - {q(v)}" for v in vals]
def block(name, text):
    lines=[f"{name}: |-"]
    for line in text.replace('\r\n','\n').replace('\r','\n').rstrip('\n').split('\n'):
        lines.append('  '+line)
    return lines

def split_fm(text):
    lines=text.splitlines()
    if not lines or lines[0].strip()!='---': raise Fail('missing front matter')
    for i in range(1,len(lines)):
        if lines[i].strip()=='---':
            body='\n'.join(lines[i+1:])
            return lines[1:i], body, text.endswith('\n')
    raise Fail('unterminated front matter')

def is_top(line):
    return line and not line.startswith((' ','\t')) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*\s*:', line)
def key_of(line): return line.split(':',1)[0].strip()

def scalar(v):
    v=v.strip()
    if v in ('true','false'): return v=='true'
    if v in ('[]',''): return [] if v=='[]' else ''
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1].replace('\\"','"').replace('\\\\','\\')
    return v

def parse_fm(lines):
    d={}; i=0
    while i<len(lines):
        line=lines[i]
        if not is_top(line): i+=1; continue
        k=key_of(line); rest=line.split(':',1)[1].strip()
        if rest in ('|-','|'):
            i+=1; vals=[]
            while i<len(lines) and not is_top(lines[i]):
                vals.append(lines[i][2:] if lines[i].startswith('  ') else lines[i]); i+=1
            d[k]='\n'.join(vals).rstrip('\n'); continue
        if rest=='':
            vals=[]; j=i+1
            while j<len(lines) and not is_top(lines[j]):
                m=re.match(r'\s*-\s*(.*)$', lines[j])
                if m: vals.append(scalar(m.group(1)))
                j+=1
            d[k]=vals; i=j; continue
        d[k]=scalar(rest); i+=1
    return d

def replace_fields(fm, record):
    repl=[]
    repl += arr('authors', record['authors'])
    repl += [f"authors_display: {q(record['authors_display'])}", "authors_complete: true", "authors_source: \"reviewed-publication-pdf\""]
    repl += block('abstract', record['abstract'])
    repl += ["abstract_source: \"reviewed-publication-pdf\""]
    repl += arr('keywords', record['keywords'])
    ks=record['keywords_status']; src='reviewed-publication-pdf' if ks=='verified' else 'publication-pdf-no-keywords'
    repl += [f"keywords_source: {q(src)}", f"keywords_status: {q(ks)}", "metadata_status: \"reviewed\"", "metadata_retrieved_at: \"2026-07-23\""]
    out=[]; inserted=False; i=0
    while i<len(fm):
        if is_top(fm[i]) and key_of(fm[i]) in TARGET:
            if not inserted: out.extend(repl); inserted=True
            i+=1
            while i<len(fm) and not is_top(fm[i]): i+=1
        else:
            out.append(fm[i]); i+=1
    if not inserted: out.extend(repl)
    return out

def load_input(path):
    if not path.exists(): raise Fail('input file does not exist')
    raw=path.read_bytes()
    try: payload=json.loads(raw.decode('utf-8'))
    except Exception as e: raise Fail(f'invalid UTF-8 JSON: {e}')
    if not isinstance(payload,dict): raise Fail('top-level JSON is not object')
    if payload.get('schema_version')!=1: raise Fail('schema_version is not 1')
    records=payload.get('records')
    if not isinstance(records,list) or len(records)!=49: raise Fail('records is not 49')
    seq=[]; ids=[]; pc=Counter(); kw=0; nokw=0
    for r in records:
        if 'sequence' not in r: raise Fail('missing sequence')
        seq.append(r['sequence']); sid=r.get('stable_id')
        if not sid: raise Fail('missing stable_id')
        ids.append(sid)
        for f in ('title','authors_display','abstract'):
            if not isinstance(r.get(f),str) or not r[f].strip(): raise Fail(f'{sid} invalid {f}')
        if not isinstance(r.get('authors'),list) or not r['authors'] or not all(isinstance(a,str) and a.strip() for a in r['authors']): raise Fail(f'{sid} invalid authors')
        if r['authors_display']!='; '.join(r['authors']): raise Fail(f'{sid} authors_display mismatch')
        if not isinstance(r.get('keywords'),list) or not all(isinstance(k,str) and k.strip() for k in r['keywords']): raise Fail(f'{sid} invalid keywords')
        if r.get('publication_type') not in ('Journal Article','Conference Paper'): raise Fail(f'{sid} invalid type')
        if r.get('review_status')!='已复核确认': raise Fail(f'{sid} invalid review_status')
        if r.get('keywords_status') not in ('verified','not-provided-in-pdf'): raise Fail(f'{sid} invalid keywords_status')
        if r['keywords_status']=='verified':
            if not r['keywords']: raise Fail(f'{sid} verified without keywords')
            kw+=1
        else:
            if r['keywords']!=[]: raise Fail(f'{sid} no-keywords has keywords')
            nokw+=1
        pc[r['publication_type']]+=1
    if len(seq)!=len(set(seq)) or len(ids)!=len(set(ids)): raise Fail('duplicate sequence or stable_id')
    actual={"publications":len(records),"journal_articles":pc['Journal Article'],"conference_papers":pc['Conference Paper'],"with_keywords":kw,"without_keywords":nokw}
    if actual!=EXPECTED or payload.get('expected_counts')!=actual: raise Fail(f'expected_counts mismatch {actual}')
    return payload, raw

def norm_title(s):
    s=unicodedata.normalize('NFKC',s).lower().strip()
    s=re.sub(r'[\s\-–—‐‑‒―:：,，.;；。!！?？"“”\'‘’()（）\[\]【】/\\]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def scan(pubdir):
    paths=sorted(pubdir.glob('*/index.md'))
    if len(paths)!=49: raise Fail(f'website publication files {len(paths)} != 49')
    items={}
    for p in paths:
        fm,body,eof=split_fm(p.read_text(encoding='utf-8'))
        d=parse_fm(fm); sid=d.get('stable_id')
        if not sid: raise Fail(f'{p} missing stable_id')
        if sid in items: raise Fail(f'duplicate stable_id {sid}')
        items[sid]=(p,fm,body,eof,d)
    return items

def generate(payload, raw, pubdir):
    items=scan(pubdir); records={r['stable_id']:r for r in payload['records']}
    if set(items)!=set(records): raise Fail('JSON stable_id set does not match website')
    new={}; snapshots={}; title_rows=[]; no_kw=[]
    for sid,r in records.items():
        p,fm,body,eof,d=items[sid]
        snapshots[sid]={k:d.get(k) for k in IMMUTABLE}
        check='match' if d.get('title')==r['title'] else ('normalized match' if norm_title(d.get('title',''))==norm_title(r['title']) else 'different')
        title_rows.append((sid,r['title'],str(p),check,'matched'))
        if r['keywords_status']=='not-provided-in-pdf': no_kw.append((sid,d.get('title','')))
        nf=replace_fields(fm,r)
        text='---\n'+'\n'.join(nf)+'\n---\n'+body
        if eof or not text.endswith('\n'): text=text.rstrip('\n')+'\n'
        # validate parsed output
        nd=parse_fm(split_fm(text)[0])
        for k in IMMUTABLE:
            if nd.get(k)!=snapshots[sid].get(k): raise Fail(f'immutable changed in generated {sid} {k}')
        if nd.get('authors')!=r['authors'] or nd.get('authors_display')!=r['authors_display'] or nd.get('authors_complete') is not True: raise Fail(f'{sid} author validation failed')
        if nd.get('abstract')!=r['abstract'].rstrip('\n'): raise Fail(f'{sid} abstract validation failed')
        if nd.get('keywords')!=r['keywords'] or nd.get('keywords_status')!=r['keywords_status'] or nd.get('metadata_status')!='reviewed': raise Fail(f'{sid} keyword/status validation failed')
        new[p]=text
    return items,new,snapshots,title_rows,no_kw

def report(path,payload,raw,title_rows,no_kw,changed,commands=None,cleanup=False,idemp='pending'):
    counts=payload['expected_counts']; sha=hashlib.sha256(raw).hexdigest()
    doi_non=doi_empty=featured=0
    for sid,_,wp,_,_ in title_rows:
        d=parse_fm(split_fm(Path(wp).read_text(encoding='utf-8'))[0])
        doi_non += bool(d.get('doi')); doi_empty += not bool(d.get('doi')); featured += d.get('featured') is True
    lines=['# Publication Metadata Import Report','', '## Input',f'- Input filename: Publication_Metadata_Final_Clean_49.txt',f'- Input repository path: {Path("Publication_Metadata_Final_Clean_49.txt")}',f'- Input SHA-256: {sha}',f'- Schema version: {payload.get("schema_version")}',f'- Data source: {payload.get("data_source")}',f'- Import date: 2026-07-23',f'- Record count: {len(payload["records"])}','', '## Counts',f'- Publications: {counts["publications"]}',f'- Journal Articles: {counts["journal_articles"]}',f'- Conference Papers: {counts["conference_papers"]}',f'- Complete author lists: 49',f'- Abstracts: 49',f'- Publications with keywords: {counts["with_keywords"]}',f'- Source PDFs without keywords: {counts["without_keywords"]}',f'- DOI records: {doi_non}',f'- Records without DOI: {doi_empty}','', '## Stable ID Matching','| Stable ID | JSON Title | Website Path | Title Check | Result |','|---|---|---|---|---|']
    for row in title_rows: lines.append('| '+' | '.join(str(x).replace('|','\\|') for x in row)+' |')
    lines += ['', '## Title Differences']
    diffs=[r for r in title_rows if r[3] != 'match']
    lines += [f'- {r[0]}: {r[3]}' for r in diffs] or ['- None']
    lines += ['', '## No-keywords Publications','| Stable ID | Title |','|---|---|']
    for sid,t in no_kw: lines.append(f'| {sid} | {t.replace("|","\\|")} |')
    lines += ['', '## Immutable Field Verification'] + [f'- {k} changed: 0' for k in IMMUTABLE]
    lines += ['', '## Imported Fields','- authors imported: 49','- authors_complete true: 49','- abstracts imported: 49','- keywords verified: 43','- keywords not provided: 6','- metadata_status reviewed: 49','', '## Changed Files']
    lines += [f'- {p}' for p in changed]
    lines += ['', '## Validation Commands'] + (commands or ['- To be updated after final validation.'])
    lines += ['', '## Idempotency',f'- files changed: {idemp}','', '## Temporary Input Cleanup',f'- Input original path: Publication_Metadata_Final_Clean_49.txt',f'- Input SHA-256: {sha}',f'- Input deleted after import, check and idempotency validation: {"yes" if cleanup else "pending"}',f'- Final PR diff contains Publication_Metadata_Final_Clean_49.txt: {"no" if cleanup else "pending"}','']
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text('\n'.join(lines),encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--publication-dir',required=True); ap.add_argument('--report',required=True); ap.add_argument('--apply',action='store_true'); ap.add_argument('--check',action='store_true')
    a=ap.parse_args()
    if a.apply and a.check: raise SystemExit('--apply and --check are mutually exclusive')
    try:
        payload,raw=load_input(Path(a.input)); items,new,snaps,rows,no_kw=generate(payload,raw,Path(a.publication_dir))
        changed=[str(p) for p,t in new.items() if p.read_text(encoding='utf-8')!=t]
        if a.check:
            if changed: raise Fail(f'check failed: {len(changed)} files differ from input')
            print('check passed: files changed: 0')
        elif a.apply:
            for p,t in new.items():
                if p.read_text(encoding='utf-8')!=t:
                    fd,tmp=tempfile.mkstemp(dir=str(p.parent),prefix='.tmp-',text=True)
                    with os.fdopen(fd,'w',encoding='utf-8') as h: h.write(t)
                    os.replace(tmp,p)
            print(f'apply passed: files changed: {len(changed)}')
        else:
            print(f'preflight passed: files to change: {len(changed)}')
        report(Path(a.report),payload,raw,rows,no_kw,[str(x[0]) for x in items.values()])
    except Fail as e:
        print('ERROR:',e,file=sys.stderr); return 1
    return 0
if __name__=='__main__': sys.exit(main())
