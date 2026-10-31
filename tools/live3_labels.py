"""Label datasets/live3: enrollment gallery, genuine and impostor probes."""
import json, os, re, sys
R = os.environ.get('LIVE3', 'datasets/live3')
D = R + '/egisdump'
ts = lambda k: sorted({f.split('_')[0] for f in os.listdir(D) if f'_{k}_f00' in f}, key=int)
enr = ts('e')
# two enrollment sessions (22:46-22:47, 22:48-22:49), split at biggest gap
gaps = [int(enr[i+1]) - int(enr[i]) for i in range(len(enr)-1)]
cut = gaps.index(max(gaps)) + 1
gallery = {'enrA': enr[:cut], 'enrB': enr[cut:]}
# genuine: verify dumps matched to the fprintd "winner" line that follows them
log = [l.split() for l in open(R + '/matchlog.txt')]
ev = [(float(l[0]), int(l[-1])) for l in log]
imp_ts = {f.split('_')[0] for d in os.listdir(R + '/impostor') for f in os.listdir(f'{R}/impostor/{d}')}
probes = []
for t in ts('v'):
    if t in imp_ts: continue
    t0 = int(t) / 1e6
    nxt = [w for s, w in ev if 0 <= s - t0 < 3]
    probes.append({'ts': t, 'winner': nxt[0] if nxt else None})
imp = {d: sorted({f.split('_')[0] for f in os.listdir(f'{R}/impostor/{d}')}, key=int) for d in os.listdir(R + '/impostor')}
json.dump({'gallery': gallery, 'probes': probes, 'impostor': imp}, open(R + '/labels.json', 'w'), indent=1)
