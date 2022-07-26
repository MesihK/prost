from .esmts25_13 import embed
from scipy.fftpack import dct, idct
import numpy as np

def iDCTquant(v,n):
    f = dct(v.T, type=2, norm='ortho')
    trans = idct(f[:,:n], type=2, norm='ortho')
    for i in range(len(trans)):
        trans[i] = scale(trans[i])
    return trans.T

def scale(v):
    M = np.max(v)
    m = np.min(v)
    return (v - m) / float(M - m)

def quant2D(emb,n=5,m=44):
    dct = iDCTquant(emb[1:len(emb)-1],n)
    ddct = iDCTquant(dct.T,m).T
    ddct = ddct.reshape(n*m)
    return (ddct*127).astype('int8')

def quantSeq(seq):
    e = embed(seq.upper())
    q25_544 = quant2D(e[1],5,44)
    q13_385 = quant2D(e[0],3,85)
    return np.concatenate([q25_544,q13_385])

def prostDistance(emb1,emb2):
    return abs(emb1-emb2).sum()/2
