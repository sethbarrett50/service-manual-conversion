#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "beautifulsoup4>=4.12,<5",
#   "reportlab>=4.2,<5",
#   "pillow>=10,<13",
#   "pymupdf>=1.24,<2",
# ]
# ///
"""Convert a LEMON offline vehicle ZIP into navigable, sectioned and combined PDFs.

Usage:
    uv run lemon_manual_builder.py 'LEMON 2014 Nissan-Datsun Frontier PRO-4X, 4D Pickup, Automatic Trans.zip' --out frontier_pdfs
    uv run lemon_manual_builder.py 'LEMON 2002 Buick LeSabre V6-3.8L VIN K.zip' --out buick_pdfs
    uv run lemon_manual_builder.py 'LEMON ...zip' --out test_pdfs --max-documents 30

Outputs: sections/*.pdf, complete_navigable_manual.pdf, sectioned_manuals.zip,
         manifest.json. Conversion is reflowed, not an exact browser print.
"""
import argparse
import html
import json
import re
import shutil
import tempfile
import zipfile
from collections import OrderedDict
from pathlib import Path
from urllib.parse import unquote, urlparse

import fitz
from bs4 import BeautifulSoup, NavigableString, Tag
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Image, PageBreak

A4 = (595.28, 841.89)
BLUE = (0.10, 0.32, 0.58)


def safe_extract_zip(zpath, destination):
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            p = (destination / info.filename).resolve()
            if not p.is_relative_to(destination.resolve()):
                raise ValueError(f'Unsafe ZIP path: {info.filename}')
        z.extractall(destination)


def find_root(path):
    possibilities = [path] + [p.parent for p in path.rglob('index.html')]
    for root in possibilities:
        if (root / 'pages' / '2.html').is_file():
            return root
    raise ValueError('No recognizable LEMON manual: missing pages/2.html')


def crumb_parts(soup):
    return [a.get_text(' ', strip=True) for a in soup.select('.header a.breadcrumb-part')][4:]


def get_section(parts):
    if not parts:
        return 'General Information'
    first = parts[0]
    if first.startswith('Repair and Diagnosis'):
        return parts[1] if len(parts) > 1 else 'General Information'
    if first in ('Labor Times', 'Parts and Labor'):
        idx = 2 if len(parts) > 2 and parts[1] == 'Other Variant' else 1
        return ('Parts and Labor - ' + parts[idx]) if len(parts) > idx else 'Parts and Labor'
    return first


def discover(root, limit=None):
    """Use breadcrumbs from numbered HTML pages rather than a shallow nav tree."""
    groups = OrderedDict()
    for f in sorted((root / 'pages').glob('*.html'), key=lambda p: int(p.stem) if p.stem.isdigit() else 10**12):
        if not f.stem.isdigit():
            continue
        soup = BeautifulSoup(f.read_bytes(), 'html.parser')
        main = soup.select_one('.main')
        if main is None:
            continue
        heading = main.find('h1')
        title = heading.get_text(' ', strip=True) if heading else f'Page {f.stem}'
        # Exclude navigation trees from content PDFs; their hierarchy is rebuilt
        # as native clickable PDF contents and bookmarks.
        anchors = main.select('a[href]')
        if 'split tree' in main.get_text(' ', strip=True)[:350].lower():
            continue
        if len(anchors) > 25:
            link_chars = sum(len(a.get_text(' ',strip=True)) for a in anchors)
            plain_chars = len(main.get_text(' ',strip=True))
            if plain_chars and link_chars / plain_chars > .55:
                continue
        # Ignore navigation-only pages, which contain menus and no actual content.
        copy = BeautifulSoup(str(main), 'html.parser')
        for tag in copy.select('ul, button, script, nav'):
            tag.decompose()
        text = copy.get_text(' ', strip=True)
        if len(text) <= len(title) + 15 and not copy.select('img, table'):
            continue
        parts = crumb_parts(soup)
        section = get_section(parts)
        groups.setdefault(section, []).append({'id':int(f.stem),'title':title,'path':' > '.join(parts)})
        if limit and sum(len(g) for g in groups.values()) >= limit:
            break
    return groups


def styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name='LTitle',parent=s['Heading1'],fontSize=14,leading=17,spaceBefore=7,spaceAfter=7,keepWithNext=True))
    s.add(ParagraphStyle(name='LCrumb',parent=s['Normal'],fontSize=7,leading=10,textColor=colors.grey,spaceAfter=8))
    s.add(ParagraphStyle(name='LBody',parent=s['BodyText'],fontSize=9,leading=12.5,spaceAfter=5))
    s.add(ParagraphStyle(name='LSubhead',parent=s['Heading3'],fontSize=10,leading=13,spaceBefore=7,spaceAfter=4,keepWithNext=True))
    s.add(ParagraphStyle(name='LFront',parent=s['Title'],fontSize=20,leading=25,alignment=TA_CENTER))
    return s


def norm(t):
    return html.escape(' '.join(t.split()),quote=False)


def image_flow(tag, root):
    src = tag.get('src')
    if not src:
        return []
    parsed = urlparse(src)
    if parsed.scheme or parsed.netloc:
        return []
    path = (root / 'pages' / unquote(parsed.path)).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return []
    try:
        w,h = ImageReader(str(path)).getSize()
        ratio = min(485/w, 670/h, 1)
        return [Image(str(path), width=w*ratio, height=h*ratio), Spacer(1,5)]
    except Exception:
        return []


def blocks(main, root, s):
    result, buf = [], []
    for t in main.select('script, button, nav'):
        t.decompose()
    def flush(style='LBody'):
        value = ''.join(buf).strip()
        buf.clear()
        if value:
            result.append(Paragraph(norm(value),s[style]))
    def walk(node):
        if isinstance(node,NavigableString):
            buf.append(str(node));return
        if not isinstance(node,Tag):
            return
        kind=node.name
        if kind=='h1': return
        if kind=='br': flush();return
        if kind=='img': flush();result.extend(image_flow(node,root));return
        if kind=='table':
            flush()
            for tr in node.select('tr'):
                values=[td.get_text(' ',strip=True) for td in tr.find_all(['th','td'])]
                if any(values):result.append(Paragraph(norm(' | '.join(values)),s['LBody']))
            return
        if kind in ('h2','h3','h4','p','pre','li'):
            flush()
            if kind=='li':buf.append('• ')
            for c in node.children:walk(c)
            flush('LSubhead' if kind.startswith('h') else 'LBody')
            return
        if kind in ('div','section','article','ul','ol','blockquote'):
            flush()
            for c in node.children:walk(c)
            flush();return
        for c in node.children:walk(c)
    for child in main.children:walk(child)
    flush()
    return result


class TaggedDoc(BaseDocTemplate):
    def __init__(self,path,label,**kwargs):
        super().__init__(str(path),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=47,bottomMargin=43,**kwargs)
        self.label=label
        frame=Frame(48,43,A4[0]-96,A4[1]-90,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
        self.addPageTemplates([PageTemplate(id='normal',frames=frame,onPage=self.footer)])
    def footer(self,canv,doc):
        canv.saveState();canv.setFont('Helvetica',7);canv.setFillColor(colors.grey)
        canv.drawString(48,25,self.label[:85]);canv.drawRightString(A4[0]-48,25,str(doc.page));canv.restoreState()
    def afterFlowable(self,flowable):
        if hasattr(flowable,'_lemon_id'):
            # reportlab creates named destinations for exact document start pages
            self.canv.bookmarkPage('item_'+str(flowable._lemon_id))


def render_batch(root, vehicle, section, docs, path):
    s=styles()
    flow=[]
    for i, entry in enumerate(docs):
        if i:flow.append(PageBreak())
        heading=Paragraph(norm(entry['title']+f"  [source {entry['id']}]"),s['LTitle'])
        heading._lemon_id=entry['id']
        flow.append(heading)
        flow.append(Paragraph(norm(entry['path']),s['LCrumb']))
        soup=BeautifulSoup((root/'pages'/f"{entry['id']}.html").read_bytes(),'html.parser')
        main=soup.select_one('.main')
        flow.extend(blocks(main,root,s) if main else [])
    TaggedDoc(path,vehicle+' — '+section,pageCompression=1).build(flow)


def clean_name(value):
    name=re.sub(r'[^a-z0-9]+','_',value.lower()).strip('_')
    return name[:90] or 'general'


def add_contents(pdf, label, entries, target_pages, contents_title='Contents'):
    """Prepend clickable index pages, then return source page shift."""
    n_per=48
    count=max(1,(len(entries)+n_per-1)//n_per)
    index=fitz.open()
    for i in range(count):
        page=index.new_page(width=A4[0],height=A4[1])
        page.insert_text((38,38),f'{label} — {contents_title} ({i+1}/{count})',fontsize=13)
        for j,entry in enumerate(entries[i*n_per:(i+1)*n_per]):
            k=i*n_per+j
            y=66+j*15.5
            title=entry['title'].replace('\n',' ')[:77]
            page.insert_text((40,y),title,fontsize=8)
            page.insert_text((548,y),str(target_pages[k]+count+1),fontsize=8)
            # Add links after index is inserted in the destination PDF.
    pdf.insert_pdf(index,start_at=0,links=False)
    index.close()
    for k, target in enumerate(target_pages):
        ipage = pdf[k // n_per]
        y = 66 + (k % n_per) * 15.5
        ipage.insert_link({'kind':fitz.LINK_GOTO,'from':fitz.Rect(35,y-12,566,y+3),'page':target+count})
    return count


def build_section(root,vehicle,section,docs,destination,temp_root,batch_size):
    destination.parent.mkdir(parents=True,exist_ok=True)
    doc=fitz.open()
    entries=[]; page_positions=[]
    for part_idx,offset in enumerate(range(0,len(docs),batch_size)):
        subset=docs[offset:offset+batch_size]
        part=temp_root/f'part_{part_idx:04}.pdf'
        print(f'    batch {part_idx+1}: {len(subset)} documents',flush=True)
        render_batch(root,vehicle,section,subset,part)
        pdf=fitz.open(part)
        # Named destinations are not preserved reliably through insert_pdf,
        # so identify each document heading using source IDs printed in the page.
        found={}
        for p in range(len(pdf)):
            text=pdf[p].get_text('text')[:1500]
            for m in re.finditer(r'\[source (\d+)\]',text):
                found.setdefault(int(m.group(1)),p)
        for item in subset:
            page_positions.append(len(doc)+found.get(item['id'],0))
            entries.append(item)
        doc.insert_pdf(pdf)
        pdf.close();part.unlink(missing_ok=True)
    offset=add_contents(doc,section,entries,page_positions)
    toc=[[1,section,1]]
    for e,p in zip(entries,page_positions):
        toc.append([2,e['title'][:110],p+offset+1])
    doc.set_toc(toc)
    doc.save(destination,garbage=0,deflate=False)
    count=len(doc)
    doc.close()
    return count


def combine_section_pdfs(section_files,destination,vehicle):
    merged=fitz.open();start_pages=[];nested=[]
    for name,p in section_files:
        d=fitz.open(p)
        start_pages.append(len(merged))
        for level,title,page in d.get_toc():
            nested.append([level+1,title,len(merged)+page])
        merged.insert_pdf(d)
        d.close()
    master=fitz.open()
    per=42
    for idx in range(0,len(section_files),per):
        pg=master.new_page(width=A4[0],height=A4[1]);pg.insert_text((40,40),vehicle+' — Master Contents',fontsize=16)
        for j,(name,_) in enumerate(section_files[idx:idx+per]):
            row=idx+j
            y=75+j*17
            pg.insert_text((44,y),name[:78],fontsize=10)
            # Link is added after inserting the master pages.
    merged.insert_pdf(master,start_at=0,links=False)
    shift=len(master); master.close()
    for row, start in enumerate(start_pages):
        pg=merged[row // per]
        y=75+(row % per)*17
        pg.insert_link({'kind':fitz.LINK_GOTO,'from':fitz.Rect(40,y-12,550,y+3),'page':start+shift})
    # Better preserve document order and outline hierarchy.
    ordered=[[1,'Master Contents',1]]
    for (name,p),start in zip(section_files,start_pages):
        ordered.append([1,name,start+shift+1])
        d=fitz.open(p)
        for level,title,page in d.get_toc():
            if level>1:
                ordered.append([level,title,start+shift+page])
        d.close()
    merged.set_toc(ordered)
    merged.save(destination,garbage=0,deflate=False)
    pages=len(merged);merged.close()
    return pages


def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source',type=Path,help='LEMON ZIP or extracted vehicle directory')
    ap.add_argument('--out',type=Path,default=Path('lemon_pdfs'))
    ap.add_argument('--max-documents',type=int,help='Small test run; limit total procedure documents')
    ap.add_argument('--batch-size',type=int,default=120,help='Documents per temporary PDF batch')
    ap.add_argument('--section',action='append',help='Only build section names containing this term; can repeat')
    ap.add_argument('--no-complete',action='store_true',help='Skip combined PDF')
    ap.add_argument('--no-zip',action='store_true',help='Skip sectioned ZIP')
    args=ap.parse_args()
    if args.batch_size<1:ap.error('--batch-size must be positive')
    args.out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lemon_build_') as tmp:
        scratch=Path(tmp)
        if args.source.is_file() and args.source.suffix.lower()=='.zip':
            print('Extracting ZIP...',flush=True)
            src=scratch/'extracted';src.mkdir()
            safe_extract_zip(args.source,src)
        else:src=args.source
        root=find_root(src)
        vehicle=root.name
        print('Indexing:',vehicle,flush=True)
        groups=discover(root,args.max_documents)
        if args.section:
            groups=OrderedDict((k,v) for k,v in groups.items() if any(term.casefold() in k.casefold() for term in args.section))
        print(f'{sum(map(len,groups.values()))} documents in {len(groups)} sections',flush=True)
        created=[];manifest=[]
        sectiondir=args.out/'sections';sectiondir.mkdir(exist_ok=True)
        for i,(section,docs) in enumerate(groups.items(),1):
            target=sectiondir/f'{i:02}_{clean_name(section)}.pdf'
            print(f'[{i}/{len(groups)}] {section}: {len(docs)} documents',flush=True)
            pages=build_section(root,vehicle,section,docs,target,scratch,args.batch_size)
            created.append((section,target))
            manifest.append({'section':section,'file':target.name,'documents':len(docs),'pages':pages})
            print(f'    => {pages} PDF pages, {target.stat().st_size//(1024*1024)} MiB',flush=True)
        if created and not args.no_complete:
            target=args.out/'complete_navigable_manual.pdf'
            print('Merging complete manual...',flush=True)
            pages=combine_section_pdfs(created,target,vehicle)
            print(f'Combined: {pages} pages, {target.stat().st_size//(1024*1024)} MiB',flush=True)
        if created and not args.no_zip:
            archive=args.out/'sectioned_manuals.zip'
            print('Packaging section PDFs...',flush=True)
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
                for _,f in created:z.write(f,arcname=f.name)
            with zipfile.ZipFile(archive) as z:
                bad=z.testzip()
                if bad:raise ValueError('ZIP failed validation at '+bad)
        (args.out/'manifest.json').write_text(json.dumps({'vehicle':vehicle,'sections':manifest},indent=2),encoding='utf-8')
    print('Done:',args.out.resolve(),flush=True)


if __name__=='__main__':
    main()
