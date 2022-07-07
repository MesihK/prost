import numpy as np
from pickle import load,loads,dump,dumps
import click
import blosc

from itertools import groupby
def fasta_iter(fastafile):
    fh = open(fastafile)
    faiter = (x[1] for x in groupby(fh, lambda line: line[0] == ">"))
    for header in faiter:
        header = next(header)[1:].strip()
        seq = "".join(s.strip() for s in next(faiter))
        yield header, seq


def check_seq(seq):
    std = ['A', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'V', 'W', 'Y']
    ambiguous = [ 'X', 'B', 'U', 'Z', 'O']
    aa = std+ambiguous
    for a in seq.upper():
        if a not in aa:
            return False,a
    return True,''

@click.command()
@click.argument('fasta', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('out', type=click.Path(exists=False,file_okay=True,dir_okay=False))
def createdb(fasta, out):
    from prosttools import quantSeq

    with open('cache.pkl','rb') as f:
        cache = load(f)
    cacheDirty = False

    quant = []
    namesd = {}
    ind = 0

    for fa in fasta_iter(fasta):
        name = fa[0]

        l = len(fa[1])
        if l < 5:
            print(name,'discarded, length:',l)
            continue

        status,offchar = check_seq(fa[1])
        if status == False:
            print(name,'contains unknown aa',offchar)
            continue

        if name in namesd:
            print(name,'is already exits!')
            assert np.shape(quant[namesd[name]])[0] == 475
            continue

        namesd[name] = ind
        ind += 1

        if fa[1] in cache:
            quant.append(cache[fa[1]])
        else:
            print(name,'not found in cache. Quantize it.')
            qseq = quantSeq(fa[1])
            quant.append(qseq)
            cache[fa[1]] = qseq
            cacheDirty = True

        assert np.shape(quant[-1])[0] == 475

    names = list(namesd.keys())

    assert len(names) == np.shape(quant)[0]
    print('Total number of sequences embedded in the db:',len(names))

    with open(out,'wb') as f:
        f.write(blosc.compress(dumps([np.array(names),np.array(quant)])))

    if cacheDirty:
        with open('cache.pkl','wb') as f:
            dump(cache,f)

@click.command()
@click.option('--thr', default=0.05, help='E-value threshold for homolog detection')
@click.argument('querydb', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('targetdb', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('out', type=click.Path(exists=False,file_okay=True,dir_okay=False))
def search(thr, querydb, targetdb, out):
    import scipy.stats as st
    from scipy.stats import median_abs_deviation

    with open(querydb,'rb') as f:
        qnames,qdb = loads(blosc.decompress(f.read()))
    with open(targetdb,'rb') as f:
        tnames,tdb = loads(blosc.decompress(f.read()))
    ldb = len(tdb)
    output = []
    
    mem = np.zeros((ldb,475),dtype='int8')
    for i,q in enumerate(qdb):
        np.subtract(tdb,q,out=mem)
        np.absolute(mem,out=mem)
        dbdiff = mem.sum(axis=1)
        m=np.median(dbdiff)
        s=median_abs_deviation(dbdiff)*1.4826
        zscore = (dbdiff-m)/s
        e = st.norm.cdf(zscore)*ldb
        res = np.where(e < thr)[0]
        sort = np.argsort(e[res])
        res = res[sort]
        dbdiff = dbdiff[res]/2
        evals = e[res]
        names = tnames[res]

        for n,diff,ev in zip(names,dbdiff,evals):
            output.append('%s\t%s\t%d\t%.2e'%(qnames[i],n,diff,ev))

    with open(out,'w') as f:
        for o in output:
            f.write(o+'\n')

@click.group()
def cli():
    pass

cli.add_command(createdb)
cli.add_command(search)

if __name__ == '__main__':
    cli()
