import torch
from esm.data import Alphabet
import numpy as np
import multiprocessing

import os
from pathlib import Path
if 'PROSTDIR' in os.environ: prostdir = os.environ['PROSTDIR']
else: prostdir = str(Path.home())+'/.config/prost'

torch.set_num_threads(multiprocessing.cpu_count())

#https://github.com/pytorch/pytorch/issues/52286
#torch._C._jit_set_bailout_depth(0) # Use _jit_set_fusion_strategy, bailout depth is deprecated.
torch._C._jit_set_profiling_mode(False)

esm1b = torch.jit.freeze(torch.jit.load(prostdir+'/traced_esm1b_25_13.pt').eval())
esm1b = torch.jit.optimize_for_inference(esm1b)
alphabet = Alphabet.from_architecture("ESM-1b")
batch_converter = alphabet.get_batch_converter()

#https://stackoverflow.com/a/63616077
#This prevents memory leak
for param in esm1b.parameters():
    pram.grad = None
    param.requires_grad = False

if torch.cuda.is_available():
    esm1b = esm1b.cuda()

def _embed(seq):
    _, _, toks = batch_converter([("prot",seq)])
    if torch.cuda.is_available():
        toks = toks.to(device="cuda", non_blocking=True)
    results = esm1b(toks)
    for i in range(len(results)):
        results[i] = results[i].to(device="cpu")[0].detach().numpy()
    return results

def embed(seq):
    l = len(seq)
    embtoks = None
    if l > 1022:
        piece = int(l/1022)+1
        part = l/piece
        for i in range(piece):
            st = int(i*part)
            sp = int((i+1)*part)
            results = _embed(seq[st:sp])
            if embtoks is not None:
                for i in range(len(results)):
                    embtoks[i] = np.concatenate((embtoks[i][:len(embtoks[i])-1],results[i][1:]),axis=0)
            else:
                embtoks = results
    else:
        embtoks = _embed(seq)
    return embtoks
