import json, os, re, sys, unicodedata

D = os.path.dirname(os.path.abspath(__file__))

EDITORIAL = re.compile(r'sporked|tasting table|green queen|taste test|mashed|kitchn|purewow|food52|chatelaine|press|coconut mama|blog|nyt|go dairy free review|feasty', re.I)

def parse_n(src):
    if not src: return None
    s = re.sub(r'\d+(?:\.\d+)?/\d+', '', src)
    counts = []
    for m in re.finditer(r'([\d][\d,]*(?:\.\d+)?)\s*([kK])?', s):
        tok, k = m.group(1), m.group(2)
        v = float(tok.replace(',', ''))
        if k: v *= 1000
        elif '.' in tok or v <= 5:
            if v.is_integer() and 2 <= v <= 5 and ('review' in s or 'rating' in s):
                counts.append(v)
            continue
        counts.append(v)
    return int(max(counts)) if counts else None

def norm(s):
    s = unicodedata.normalize('NFKD', str(s).lower())
    return ''.join(ch for ch in s if ch.isalnum())

GROUPS = {  # sku file -> subs it replaces
    'sku_cheese.json': ['cheese'],
    'sku_cream_cheese.json': ['cream cheese'],
    'sku_butter.json': ['butter'],
    'sku_yogurt.json': ['yogurt'],
    'sku_milk.json': ['milk'],
    'sku_ice_cream.json': ['ice cream'],
    'sku_creams.json': ['sour cream & whips', 'coffee creamers'],
    'sku_chicken.json': ['chicken'],
    'sku_staples.json': ['tofu', 'tempeh', 'seitan'],
    'sku_eggs.json': ['eggs'],
}

# lines the SKU agents confirmed are off the market; drop even if no SKU covers them
DROP_LINES = {('followyourheart', 'veganegg')}

d = json.load(open(os.path.join(D, 'data', 'all_products_v2.json')))
old = d['products']
out = []
covered_subs = set()
report = {}

for fname, subs in GROUPS.items():
    path = os.path.join(D, 'data', fname)
    if not os.path.exists(path):
        print('MISSING', fname, '- keeping line rows for', subs)
        continue
    skus = json.load(open(path))['skus']
    lines = {(norm(p['brand']), norm(p['product'])): p for p in old if p['sub'] in subs}
    used_lines = set()
    n_rows = 0
    for s in skus:
        key = (norm(s['brand']), norm(s['line']))
        parent = lines.get(key)
        if parent is None:
            # try matching by brand alone if the brand has exactly one line here
            cands = [p for (b, _), p in lines.items() if b == norm(s['brand'])]
            parent = cands[0] if len(cands) == 1 else None
        if parent is None:
            report.setdefault('orphan', []).append(f"{fname}: {s['brand']} | {s['line']}")
            continue
        used_lines.add((norm(parent['brand']), norm(parent['product'])))
        row = {k: parent.get(k) for k in ['cat', 'sub', 'type', 'base', 'attributes', 'famous', 'buzz']}
        row['brand'] = parent['brand']
        row['line'] = parent['product']
        row['product'] = s['sku']
        row['flavor'] = s.get('flavor')
        row['pick'] = bool(s.get('recommended'))
        row['notes'] = s.get('notes') or parent.get('notes')
        if s.get('rating') is not None:
            row['rating'] = s['rating']
            row['rating_source'] = s.get('rating_source')
        elif parent.get('rating') is not None:
            row['rating'] = parent['rating']
            row['rating_source'] = (parent.get('rating_source') or '') + ' (line)'
        else:
            row['rating'] = None
            row['rating_source'] = None
        out.append(row)
        n_rows += 1
    # keep any line the agent did not cover at all
    kept = 0
    for key, p in lines.items():
        if key in DROP_LINES:
            continue
        if key not in used_lines:
            p = dict(p)
            p['line'] = p['product']
            p['pick'] = bool(p.get('buy'))
            out.append(p); kept += 1
    covered_subs.update(subs)
    report[fname] = f'{n_rows} skus + {kept} uncovered lines'

# subs not covered by any file (shouldn't happen)
for p in old:
    if p['sub'] not in covered_subs:
        p = dict(p); p['line'] = p['product']; p['pick'] = bool(p.get('buy'))
        out.append(p)

# dedupe within (brand, product)
seen, dd = set(), []
for p in out:
    k = (norm(p['brand']), norm(p['product']))
    if k in seen: continue
    seen.add(k); dd.append(p)

# recompute weighted scores
rated = [p for p in dd if p['rating'] is not None]
C = sum(p['rating'] for p in rated) / len(rated)
M = 30
for p in dd:
    p.pop('buy', None)
    if p['rating'] is None:
        p['reviews_n'] = None; p['adj'] = None; continue
    n = parse_n(p.get('rating_source'))
    if n is None:
        n = 25 if EDITORIAL.search(p.get('rating_source') or '') else 3
    if '(line)' in (p.get('rating_source') or ''):
        n = min(n, 20)  # inherited line rating: cap the evidence it carries
    p['reviews_n'] = n
    p['adj'] = round((n * p['rating'] + M * C) / (n + M), 2)

json.dump({'products': dd}, open(os.path.join(D, 'data', 'all_skus.json'), 'w'))
cats, subs_c = {}, {}
for p in dd:
    cats[p['cat']] = cats.get(p['cat'], 0) + 1
    subs_c[p['sub']] = subs_c.get(p['sub'], 0) + 1
print('TOTAL', len(dd), '| rated', len([p for p in dd if p['rating'] is not None]),
      '| brands', len({p['brand'] for p in dd}), '| picks', len([p for p in dd if p.get('pick')]))
print('cats:', cats)
print('subs:', dict(sorted(subs_c.items())))
for k, v in report.items():
    if k != 'orphan': print(' ', k, v)
if report.get('orphan'):
    print('ORPHANS (dropped):', *report['orphan'], sep='\n  ')
