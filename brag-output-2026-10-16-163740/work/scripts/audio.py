import math, random, struct, wave, json
SR=44100; DUR=25.0; N=int(SR*DUR)
tl=json.load(open('timeline.json'))
random.seed(7)
def hz(m): return 440*2**((m-69)/12)
def buf(): return [0.0]*N
music=[buf(),buf()]; fx=[buf(),buf()]
def add(dst,start,samples,gain=1.0,pan=0.0):
    i0=int(start*SR); l=gain*math.cos((pan+1)*math.pi/4); r=gain*math.sin((pan+1)*math.pi/4)
    L,R=dst
    for k,s in enumerate(samples):
        i=i0+k
        if 0<=i<N: L[i]+=s*l; R[i]+=s*r
def env(n,a,d,s_lvl,rel,total):
    out=[]
    for k in range(n):
        t=k/SR
        if t<a: e=t/a
        elif t<a+d: e=1-(1-s_lvl)*(t-a)/d
        elif t<total-rel: e=s_lvl
        else: e=s_lvl*max(0,(total-t)/rel)
        out.append(e)
    return out
def pad(m,dur):
    n=int(dur*SR); f=hz(m); e=env(n,.6,.4,.85,.9,dur); out=[]
    ph=[random.random() for _ in range(3)]; det=[0.996,1.0,1.004]
    lp=0.0
    for k in range(n):
        t=k/SR
        s=sum(math.sin(2*math.pi*(f*d*t+p))+.25*math.sin(4*math.pi*(f*d*t+p)) for d,p in zip(det,ph))/3
        lp+= (s-lp)*0.25
        out.append(lp*e[k])
    return out
def pluck(m,dur=.9,bright=.5):
    n=int(dur*SR); f=hz(m); out=[]
    for k in range(n):
        t=k/SR; e=math.exp(-t*5.5)*min(1,t/.004)
        out.append(e*(math.sin(2*math.pi*f*t)+bright*math.exp(-t*14)*math.sin(4*math.pi*f*t)+.15*math.sin(6*math.pi*f*t)*math.exp(-t*20)))
    return out
def kick():
    n=int(.35*SR); out=[]; ph=0
    for k in range(n):
        t=k/SR; f=45+70*math.exp(-t*30); ph+=2*math.pi*f/SR
        out.append(math.sin(ph)*math.exp(-t*9)*min(1,t/.002))
    return out
def hat():
    n=int(.06*SR); out=[]; prev=0
    for k in range(n):
        w=random.uniform(-1,1); hp=w-prev; prev=w
        out.append(hp*math.exp(-k/SR*70))
    return out
def bass(m,dur):
    n=int(dur*SR); f=hz(m); e=env(n,.02,.3,.7,.25,dur)
    return [e[k]*(math.sin(2*math.pi*f*k/SR)+.2*math.sin(4*math.pi*f*k/SR)) for k in range(n)]
def bell(m,dur=2.2):
    n=int(dur*SR); f=hz(m); out=[]
    for k in range(n):
        t=k/SR; e=math.exp(-t*2.2)*min(1,t/.003)
        out.append(e*(math.sin(2*math.pi*f*t)+.4*math.sin(2*math.pi*f*2.76*t)*math.exp(-t*4)+.2*math.sin(2*math.pi*f*5.4*t)*math.exp(-t*8)))
    return out
def whoosh(dur,rise=True):
    n=int(dur*SR); out=[]; lp=0; bp=0
    for k in range(n):
        x=k/n; e=(x if rise else 1-x)**1.6*math.sin(math.pi*min(1,x*1.05))
        c=.02+.18*(x if rise else 1-x)
        w=random.uniform(-1,1); lp+=(w-lp)*c; bp+=(lp-bp)*c
        out.append((lp-bp)*e*3)
    return out
BAR=2.5; BEAT=BAR/4
M=tl['meet']
# ---- pain (0-M): D minor, tense 16th pulse, dark filtered pad
for m in (38,45,50,53):
    add(music,0,pad(m,M+.4),.05 if m>40 else .07)
for i in range(int(3.75/(BEAT/2))):
    t=i*BEAT/2
    add(music,t,bass(38 if (i//4)%2==0 else 39,BEAT/2*.8),.10)
    add(music,t+BEAT/4,hat(),.03,.3*(1 if i%2 else -1))
for q in range(6): add(music,q*BEAT,kick(),.30)
# thumb-flick swipes under the scroll
for k in range(7): add(fx,k*.52,whoosh(.32,False),.025,(-.3 if k%2 else .3))
# need (3.75-M): hats drop, suspended chord holds, riser into the lift
for m in (50,57,62,64): add(music,3.75,pad(m,M-3.75+.3),.05,(m-57)/10)
add(music,3.75,bell(74,2.5),.05)
add(fx,M-1.6,whoosh(1.6,True),.07)
# ---- lift (M..): D major
chords=[[50,57,61,64,66],[47,54,57,61,62],[43,50,54,57,59],[45,52,54,57,61],[50,57,61,64,66],[47,54,57,61,64],[43,50,54,59,62],[50,57,62,64,69]]
roots=[38,35,31,33,38,35,31,38]
for b,ch in enumerate(chords):
    st=M+b*BAR
    if st>=25: break
    d=min(BAR+0.9,25-st) if b<6 else 25-st
    for i,m in enumerate(ch[1:]):
        add(music,st,pad(m+12 if b==0 else m,d),.055,(-.5+i*.33))
    if b>=1 and b<6: add(music,st,bass(roots[b],BAR*.95),.20)
for i,m in enumerate([74,78,81,86]): add(music,M+.02+i*.06,bell(m,2.8),.07,(-.3+i*.2))
add(music,M,kick(),.4)
END=20.9
for b in range(1,6):
    ch=chords[b]; seq=[ch[1]+12,ch[3]+12,ch[2]+12,ch[4]+12,ch[3]+12,ch[1]+24,ch[4]+12,ch[2]+12]
    for i,m in enumerate(seq):
        t=M+b*BAR+i*BEAT/2
        if t<END: add(music,t,pluck(m,.7,.3),.07,(-.35 if i%2 else .35))
    for q in (0,2):
        t=M+b*BAR+q*BEAT
        if t<END: add(music,t,kick(),.40)
    if b>=2:
        for e in range(8):
            t=M+b*BAR+e*BEAT/2+BEAT/4
            if t<END: add(music,t,hat(),.03,.2)
add(music,tl['logo'],kick(),.35)
for i,m in enumerate([74,78,81,85]): add(music,tl['logo']+.02+i*.05,bell(m,3.6),.05,(-.3+i*.2))
# FX in key
for c,m in zip(tl['clicks'],[86,88,90,93,86]): add(fx,c,pluck(m,.25,.1),.06,.15)
for p,m in zip(tl['pops'],[78,81,83]): add(fx,p,bell(m,.9),.04,-.15)
add(fx,tl['preview'],bell(86,1.4),.045)
for w in tl['whoosh'][1:]: add(fx,w-0.45,whoosh(.6),.05)
for i,m in enumerate([74,78,81,86,90]): add(fx,tl['fly'][0]+i*.12,pluck(m,.35,.15),.045,(-.4+i*.2))
for m in (86,90,93): add(fx,tl['hit'],bell(m,1.6),.04)
for i in range(8):
    t=tl['count'][0]+i*(tl['count'][1]-tl['count'][0])/8
    add(fx,t,pluck(81+[0,2,4,7,9,12,14,16][i],.15,0),.022)
def write(name,st):
    with wave.open(name,'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        pk=max(max(abs(x) for x in st[0]),max(abs(x) for x in st[1]),1e-6)
        g=0.7/pk if pk>0.7 else 1
        fr=bytearray()
        for a,b in zip(*st): fr+=struct.pack('<hh',int(max(-1,min(1,a*g))*32767),int(max(-1,min(1,b*g))*32767))
        w.writeframes(fr)
        print(name,'peak',round(pk,3))
write('music.wav',music); write('fx.wav',fx)
