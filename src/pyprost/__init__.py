import os
import urllib.request
from pathlib import Path

if 'PROSTDIR' in os.environ: prostdir = os.environ['PROSTDIR']
else: prostdir = str(Path.home())+'/.config/prost'
if not os.path.exists(prostdir): os.makedirs(prostdir)

if not os.path.exists(prostdir+'/traced_esm1b_25_13.pt'):
    print("Downloading ESM1b weights")
    link='https://iastate.box.com/shared/static/f9wjrsxr6uh863sc71nfeztrcxjugxgg.pt'
    urllib.request.urlretrieve(link, prostdir+'/traced_esm1b_25_13.pt')
    print("Done.")

if not os.path.exists(prostdir+'/cache.pkl'):
    print("Downloading PROST cache")
    link='https://iastate.box.com/shared/static/0xd3wnevkxuocfk9ztioleujngrs6wn5.pkl'
    urllib.request.urlretrieve(link, prostdir+'/cache.pkl')
    print("Done.")

if not os.path.exists(prostdir+'/sp.01.22.prdb'):
    print("Downloading SwissProt January 2022 Database")
    link='https://iastate.box.com/shared/static/5irpv5htzdzkfkm3jpf8riv18kivlq0f.prdb'
    urllib.request.urlretrieve(link, prostdir+'/sp.01.22.prdb')
    print("Done.")
    
from .prosttools import quantSeq,prostDistance
