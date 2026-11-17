"""Probe for grader v4: on the synthetic sample, how far does the fitted motion move the pivot in the reference and
in the center-pivot copy? (G5's changed-pixel fraction is ~0 for both on flat colours.)

    python3 src/synth/g5_probe.py      # needs validation/results_synth.json and cached frames; writes results/synth_g5_probe.json
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import framecache as FC  # noqa: E402
import graders as G  # noqa: E402
res=json.load(open(ROOT / 'validation/results_synth.json'))
out={}
for tid in sorted(res):
    td=ROOT / 'tasks_synth' / tid; spec=json.load(open(td/'spec.json'))
    orig=np.array(Image.open(td/'image.png').convert('RGB'))
    allowed=G.load_mask(td,'allowed.png'); target=G.load_mask(td,'target.png'); skull=G.load_mask(td,'skull.png')
    for v in ('ref','center_pivot'):
        fr=FC.load(FC.page_key(ROOT / 'validation/synth'/tid/v,td,spec['width'],spec['height']),td)[0]
        tg=G.track_groups(fr,orig,G.foreground(orig),allowed,G.part_groups(td,target),skull,spec)
        rows=[]
        for i,(x,y) in enumerate(spec['pivots']):
            k=i if len(tg)==len(spec['pivots']) else 0
            P,tr,Ts=tg[k]
            if tr is None: rows.append(None); continue
            d=[float(np.hypot(*(np.array(tr.apply(T,x,y))-(x,y)))) for T in Ts]
            m=[T[3] for T in Ts]
            rows.append((round(max(d),2), round(min(m),2), int(P.sum())))
        out[f'{tid}/{v}']=dict(rows=rows,frac=res[tid][v]['G5'].get('frac'))
    json.dump(out, open(ROOT / 'results/synth_g5_probe.json', 'w'), indent=1)
