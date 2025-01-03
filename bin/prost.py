#!/usr/bin/env python

import numpy as np
import scipy.stats as st
from pickle import load,loads,dump,dumps
import click
import blosc
from statsmodels.stats.multitest import multipletests
import re
from datetime import datetime
import json
import sys
from multiprocessing import Pool

import os
from pathlib import Path
if 'PROSTDIR' in os.environ: prostdir = os.environ['PROSTDIR']
else: prostdir = str(Path.home())+'/.config/prost'

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

def parseName(name):
    if type(name) == tuple: return name
    res = re.search(r"\|([\w]+)\|(\w+_\w+) (.*) OS=(.*) OX=(\d+) GN=(.*) PE=",name)
    if res is None:
        res = re.search(r"\|([\w]+)\|(\w+_\w+) (.*) OS=(.*) OX=(\d+) PE=",name)
        if res is None:
            return (name,'','','','','')
        return (res.group(1),res.group(2),res.group(3),res.group(4),res.group(5),'')
    else:
        return (res.group(1),res.group(2),res.group(3),res.group(4),res.group(5),res.group(6))

def annotate(ind,evals,go,goFrq,goDesc):
    spTotalCnt = goFrq['count']
    gores = go[ind]

    #count go term frequencies in the hits
    totalCnt = 0
    goDict = {}
    for r in gores:
        for term in r:
            if term not in goDict: goDict[term] = 1
            else: goDict[term] += 1
            totalCnt += 1
    #dont perform significance test on annotationless proteins, but count them
    goDict.pop('', None)
    if len(goDict) < 1: return []

    #perform significance test
    plist = []
    for g,cnt in goDict.items():
        contTable=[[cnt,goFrq[g]],[totalCnt,spTotalCnt]]
        _,p,_,_ = st.chi2_contingency(contTable)
        plist.append([g,p])
    if len(plist) < 1: return []

    #apply multiple p test correction
    corrp = list(multipletests([s[1] for s in plist], method="bonferroni")[1])

    #find p<0.001
    significant = list()
    for i,p in enumerate(corrp):
        if p < 0.001:
            #print(plist[i][0],goDesc[plist[i][0]])
            prot_evals = []
            prot_inds = []
            for pind,prot in enumerate(ind):
                if plist[i][0] in go[prot]:
                    #print(prot,evals[pind])
                    prot_evals.append(evals[pind])
                    prot_inds.append(prot)
            prot_pvals =  1 - np.exp(-np.array(prot_evals))
            p2 = st.combine_pvalues(prot_pvals,method='stouffer')[1]
            #apply multiple correction to new pval.
            #Then multiply this with 10 to get 0.05-> 0.5 then substract this from 1 to get 0.5 confidence for 0.05 pval.
            conf = 1-p2*len(prot_evals)*10
            #print(len(prot_evals),p,p2,p2*len(prot_evals),conf)

            #if combined e-values produces p<0.001 then and add the description
            if p2 < 0.05:
                significant.append([plist[i][0],goDesc[plist[i][0]],conf,prot_inds[0],prot_evals[0],len(prot_evals)])

    #sort by the list by increasing p value
    #significant.sort(reverse=False,key=lambda x: x[2])

    #sort by the list by decreasing confidence
    significant.sort(reverse=True,key=lambda x: x[2])
    return significant

@click.command()
@click.argument('gocsv', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('goobo', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('prdb', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('out', type=click.Path(exists=False,file_okay=True,dir_okay=False))
def mkgo(gocsv, goobo, prdb, out):
    '''mkgo command creates GO databse suitable for PROST.
mkcache command gets go tab file in csv format, GO descriptions in obo format,
and a PROST database to create a go annotations file.

It will create an output file that contains [go,freq,desc] lists.
'''

    print("Read the go csv file",gocsv)
    go = {}
    with open(gocsv,'r') as f:
        for line in f:
            id,golist = line.strip().split(',')
            go[id] = (list(set(golist.replace(' ','').split(';'))))

    print("Read the PROST database",prdb)
    with open(prdb,'rb') as f:
        qnames,qdb = loads(blosc.decompress(f.read()))

    print("Gather GO annotations for proteins in the database")
    godb = np.empty(len(qnames),dtype=object)
    for i,name in enumerate(qnames):
        id = name.split('|')[1]
        godb[i] = go[id]


    print("GO Frequencies: count the occurances of terms")
    frq = {}
    totalCnt = 0
    for l in godb:
        for term in l:
            if term in frq: frq[term] += 1
            else: frq[term] = 1
            totalCnt += 1

    itm = list(frq.items())


    uniqueTermCnt = len(frq)
    print("Total term count:",totalCnt, "Unique term count:",uniqueTermCnt)

    frq['count'] = totalCnt
    frq['uniqueTerm'] = uniqueTermCnt

    print("Prepare GO descriptions from",goobo)
    state = 0
    id = ''
    terms = {}

    with open(goobo,'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('[Term]'):
                state = 1
                continue
            if state == 1:
                id = line.split(' ')[1]
                state = 2
                continue
            if state == 2:
                if id not in terms:
                    terms[id] = line.split(': ')[1]
                    state = 0
                else:
                    print('error',id,line,'exists in the dictionary',terms[id])


    item = list(terms.items())


    print("Look at swissprot annotations and if they dont have description then add empty one")
    cnt = 0
    for g in frq.keys():
        if g.startswith('GO:'):
            if g not in terms:
                cnt +=1
                terms[g] = ''

    print('Empty description count',cnt)

    print(len(godb),len(qdb),len(qnames),len(frq),len(terms))
    with open(out,'wb') as f:
        dump([godb,frq,terms],f)


@click.command()
@click.option('-t', '--test', is_flag=True, default=False, help='Test random 1000 embeddings')
@click.argument('fasta', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('prdb', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('out', type=click.Path(exists=False,file_okay=True,dir_okay=False))
def mkcache(test, fasta, prdb, out):
    '''mkcache command gets a fasta file and a PROST database to create a cache file.
Cache files are dictionary which consist of amino acid sequence keys and PROST embedding values.
This command should be run on unparsed PROST databases (no parseUniprotNames)'''
    from random import sample
    from pyprost import quantSeq
    prdbdict = {}
    with open(prdb,'rb') as f:
        qnames,qdb = loads(blosc.decompress(f.read()))
    for i,n in enumerate(qnames):
        prdbdict[n] = qdb[i]

    cache = {}
    seq = {}
    seq2 = []
    for fa in fasta_iter(fasta):
        name = fa[0]
        if name not in prdbdict:
            print('could not found',name,len(fa[1]))
            continue
        #if fa[1] in cache:
        #    print('already exists',fa[0],fa[1])
        cache[fa[1]] = prdbdict[name]
        seq[name] = fa[1]
        seq2.append(fa[1])

    with open(out,'wb') as f:
        dump(cache,f)

    print('PROST db size:',len(qdb),'cache size:',len(cache.keys()),'unique seq size',len(set(seq2)))
    if test:
        print("Testing random 1000 entries by re quantizing them and checking if the cached version is the same")
        for i in sample(range(len(qdb)), 1000):
            name = qnames[i]
            s = seq[name]
            quant = qdb[i]
            q = quantSeq(s)
            if not np.array_equal(cache[s], quant):
                print('DB Cache missmatch!',i,name,s)
            if np.sum(np.abs(cache[s]-q)) > 2:
                print('Cache Quant missmatch!',i,np.sum(np.abs(cache[s]-q)),name,s)


@click.command()
@click.argument('prdb', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('out', type=click.Path(exists=False,file_okay=True,dir_okay=False))
def parseUniprotNames(prdb, out):
    '''PROST python package v0.1 parseUniprotNames command.
parseUniprotNames commend gets a PROST database file and parses the names by:
[UniprotID, Name, Type, Organism, OrganismID, Gene]
and saves upated PROST database to out argument.'''
    import re

    with open(prdb,'rb') as f:
        qnames,qdb = loads(blosc.decompress(f.read()))
    names = np.empty(len(qnames),dtype=object)
    for i,name in enumerate(qnames):
        names[i] = parseName(name)

    print(len(names),names[0],names[-1])

    with open(out,'wb') as f:
        f.write(blosc.compress(dumps([names,qdb])))
@click.command()
@click.option('-n', '--no-cache', is_flag=True, default=False, help='Disable embedding caching')
@click.option('-s', '--split', default=0, type=int, help='Split output into files of specified size (0 for no split)')
@click.argument('fasta', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('out', type=click.Path(exists=False,file_okay=True,dir_okay=False))
def makedb(no_cache, split, fasta, out):
    '''makedb command creates PROST databases from FASTA files.
makedb command gets a fasta file and creates a PROST database that can be used as query or target database in a search.'''
    from pyprost import quantSeq

    cache = {}
    cacheDirty = False
    file_ind = 0

    if not no_cache:
        if os.path.exists(prostdir+'/cache.pkl'):
            with open(prostdir+'/cache.pkl','rb') as f:
                cache = load(f)

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

        if split > 0 and len(quant) >= split:
            split_names = list(namesd.keys())[-split:]
            split_quant = quant[-split:]
            split_filename = f"{os.path.splitext(out)[0]}_{file_ind}.prdb"
            with open(split_filename, 'wb') as f:
                f.write(blosc.compress(dumps([np.array(split_names), np.array(split_quant)])))
            print(f'Written split file: {split_filename} with {len(split_names)} entries')
            quant = quant[:-split]
            file_ind += 1

    if len(quant) > 0:
        final_filename = f"{os.path.splitext(out)[0]}_{file_ind}.prdb" if split > 0 else out
        with open(final_filename, 'wb') as f:
            f.write(blosc.compress(dumps([np.array(list(namesd.keys())[-len(quant):]), np.array(quant)])))
        print(f'Written {"final " if split > 0 else ""}file: {final_filename} with {len(quant)} entries')

    if not no_cache and cacheDirty:
        with open(prostdir+'/cache.pkl','wb') as f:
            dump(cache,f)

@click.command()
@click.argument('input_files', nargs=-1, type=click.Path(exists=True))
@click.argument('output_file', type=click.Path(exists=False))
def mergedbs(input_files, output_file):
    """Merges multiple PROST databases into one.

    Args:
        input_files: List of input PROST databases
        output_file: Path to write combined database
    """
    all_names = []
    all_quant = []

    for file in input_files:
        try:
            with open(file, 'rb') as f:
                names, db = loads(blosc.decompress(f.read()))
                all_names.extend(names)
                all_quant.extend(db)
                print(f"Processing {file}, number of entries: {len(db)}")
        except Exception as e:
            print(f"Error processing {file}: {str(e)}", err=True)
            continue

    try:
        with open(output_file, 'wb') as f:
            combined = blosc.compress(dumps([np.array(all_names), np.array(all_quant)]))
            f.write(combined)
        print(f"Successfully combined {len(input_files)} files into {output_file} with {len(all_quant)} entries.")
    except Exception as e:
        print(f"Error writing output file: {str(e)}", err=True)

def _search_worker(thr, gothr, qnames,qdb,tnames,tdb, go,goFrq,goDesc, mem, taskInd, n):
    lqdb = len(qdb)
    ldb = len(tdb)
    start = int(lqdb/n*taskInd)
    stop = int(lqdb/n*(taskInd+1))
    if stop > lqdb: stop = lqdb
    #print(taskInd,n,start,stop)
    homologList, goList = {},{}
    for i,q in enumerate(qdb[start:stop]):
        qname = parseName(qnames[i+start])[0]
        goList[qname] = []
        homologList[qname] = []
        print(f'[{taskInd:02d}] Searching for {qname}')
        np.subtract(tdb,q,out=mem)
        np.absolute(mem,out=mem)
        dbdiff = mem.sum(axis=1)
        m=np.median(dbdiff)
        s=st.median_abs_deviation(dbdiff)*1.4826
        zscore = (dbdiff-m)/s
        e = st.norm.cdf(zscore)*ldb
        res = np.where(e < thr)[0]
        sort = np.argsort(e[res])
        res = res[sort]
        dbdiff = dbdiff[res]/2
        evals = e[res]
        names = tnames[res]

        if go is not None:
            res2 = np.where(e < gothr)[0]
            sort2 = np.argsort(e[res2])
            res2 = res2[sort2]
            for a in annotate(res2,e[res2],go,goFrq,goDesc):
                goList[qname].append([a[0], a[1], f'{a[2]:.3f}', parseName(tnames[a[3]])[0], a[5], f'{a[4]:.2e}'])

        for n,diff,ev in zip(names,dbdiff,evals):
            n = parseName(n)
            homologList[qname].append([n[0], n[1], n[2], n[3], diff, f'{ev:.2e}'])
    return goList,homologList
def _search(thr, gothr, querydb, targetdb, godb,n):
    if godb != None:
        with open(godb,'rb') as f:
            go,goFrq,goDesc = load(f)
    with open(querydb,'rb') as f:
        qnames,qdb = loads(blosc.decompress(f.read()))
    with open(targetdb,'rb') as f:
        tnames,tdb = loads(blosc.decompress(f.read()))
    ldb = len(tdb)
    homologList, goList = {},{}

    mem = np.zeros((n,ldb,475),dtype='int8')
    with Pool(n) as pool:
        if godb != None: items = [(thr, gothr, qnames,qdb,tnames,tdb, go,goFrq,goDesc, mem[i], i, n) for i in range(n)]
        else: items = [(thr, gothr, qnames,qdb,tnames,tdb, None,None,None, mem[i], i, n) for i in range(n)]
        for result in pool.starmap(_search_worker, items):
            homologList.update(result[1])
            goList.update(result[0])
    return goList,homologList

def toTSV(goList,homologList,out):
    with open(out+'.tsv','w') as f:
        for queryP in homologList:
            for go in goList[queryP]:
                f.write(f'{queryP}\t'+'\t'.join([str(i) for i in go])+'\n')
            for hom in homologList[queryP]:
                f.write(f'{queryP}\t'+'\t'.join([str(i) for i in hom])+'\n')

def createAlignmentPage(p1,p2):
    return {
        "h2:caption":f"{p1} & {p2} Alignment",
        "md:info":f"Alignment of [{p1}](https://www.uniprot.org/uniprotkb/{p1}) and it's homolog [{p2}](https://www.uniprot.org/uniprotkb/{p2}) found by PROST",
        "alnpdb:test":{
            "pdb1":f"https://alphafold.ebi.ac.uk/files/AF-{p1}-F1-model_v4.pdb",
            "pdb2":f"https://alphafold.ebi.ac.uk/files/AF-{p2}-F1-model_v4.pdb",
            "alnpdb":"",
            "lineLen":120
        }
    }

def toJSONWP(queryDB,targetDB,thr,gothr,info,align,goList,homologList,prots,out):
    # Retrieve time of day and date
    now = datetime.now()
    time_of_day = now.strftime("%H:%M:%S")  # Format time as hours:minutes:seconds
    date = now.strftime("%Y-%m-%d")  # Format date as year-month-day
    cnt = 0

    jsonwp = {
        'md:caption':'## [PROST](https://www.pnas.org/doi/10.1073/pnas.2211823120) v0.2.15 Search Results',
        'md:info':f'{info}',
        'md:info2':f'This search was conducted at {time_of_day} on {date}.'
        }
    if queryDB is not None and targetDB is not None:
        jsonwp['md:info1'] = f'The query database is **{queryDB}** and the target database is **{targetDB}**.'
    if thr is not None and gothr is not None:
        jsonwp['md:info3'] = f'The e-value threshold for homology detection is **{thr}** and the threshold for GO annotation enrichment is **{gothr}**'
    jsonwp['h3:tablecap'] = 'Query Database Proteins'
    jsonwp['md:info4'] = 'Please click the link under the "Query Protein" column to access results for each query protein listed'
    jsonwp['table:proteinList'] = {'columns':['l:Query Protein','# Homologs','# GO','Best Homolog','Best H. e-val'],'rows':[]}
    jsonwp['navpage:about'] = {'md:info5':'''### PROST Method
The Protein Language Search Tool (**PROST**) is a highly accurate and efficient homology search tool designed for remote homology prediction tasks. In comparison to the current state-of-the-art tools, such as CS-BLAST or PHMMER, PROST outperforms them in terms of accuracy and speed. PROST utilizes a protein language model and quantization technique to represent proteins in a numerical format that retains their biophysical, biochemical, and evolutionary information. PROST calculates the distances of all proteins in the database to the user's query protein and performs a statistical test based on the Z-Score of the distance distribution over the entire database. The results are presented with an expected value (e-value) that estimates the likelihood of a match occurring by chance. This value is calculated from the CDF of the z-score and is corrected for multiple testing using the Bonferroni method.

### Automatic GO Enrichment Analysis
The GO annotation enrichment pipeline in PROST allows for the selection of a different e-value cutoff. This threshold determines the level of significance for the enrichment analysis. To assess the significance of the enriched GO terms, contingency tables are constructed by comparing the frequency of individual GO terms in homologs and the Swissprot database. A term-specific p-value is then calculated by subjecting the contingency table to the Chi-square test. Subsequently, Bonferroni multiple p-test corrections are applied to correct the p-values for each term. Any GO term with a p-value greater than 0.001 is removed from the analysis. The remaining GO terms are evaluated based on their source proteins' e-values, which are combined using Stouffer’s method. The resulting GO terms are subjected to another round of multiple test correction, and the enriched terms are reported..

### Manuscript
PROST manuscript can be accessed form this [link](https://www.pnas.org/doi/10.1073/pnas.2211823120). Please cite if you used PROST for finding homologs.

### Python Package
PROST [python package](https://github.com/MesihK/prost) can be used to generate this result webpage with the help of JSONWP visualizer. Please cite both of the work (PROST and JSONWP)

### Citations

``` 
@article{kilinc2023improved,
  title={Improved global protein homolog detection with major gains in function identification},
  author={Kilinc, Mesih and Jia, Kejue and Jernigan, Robert L},
  journal={Proceedings of the National Academy of Sciences},
  volume={120},
  number={9},
  pages={e2211823120},
  year={2023},
  publisher={National Acad Sciences}
}
```
'''}
    jsonwp['navpage:disclaimer'] = {
       'p:disc':'For documents and software available from this server, we do not warrant or assume any legal liability or responsibility for the accuracy, completeness, or usefulness of any information, product, or process disclosed. We do not endorse or recommend any commercial products, processes, or services. Some pages may provide links to other Internet sites for the convenience of users. We are not responsible for the availability or content of these external sites, nor do we endorse, warrant, or guarantee the products, services, or information described or offered at these other Internet sites. Information that is created by this site is within the public domain. It is not the intention to provide specific medically related advice but rather to provide users with information for better understanding. However, it is requested that in any subsequent use of this work, PROST be given appropriate acknowledgment. We do not collect any personally identifiable information (PII) about visitors to our Web sites.'
   }
    for queryP in prots:
        jsonwp[f'page:{queryP}'] = {
            'h2:caption':f'PROST Results for {queryP}',
            'h3:goCaption':'GO Annotations',
            'md:info1':'Link under "GO Term" column directs user to amigo geneontology website for a detailed inspection of the GO term',
            'table:goList':{'columns':['l:GO Term','Description','Confidence','Source','# Proteins','e-val'],'rows':[]},
            'h3:homCaption':'Putative Homologs',
            'md:info2':'Links under "Uniprot" column directs user to Uniprot website for a detailed inspection. Links under "e-value" column opens sequence alignment and protein structure visualization page',
            'table:homList':{'columns':['l:Uniprot','Name','Type','Organim','Distance','l:e-value'],'rows':[]}
        }
        if queryP in goList:
            for go in goList[queryP]:
                jsonwp[f'page:{queryP}']['table:goList']['rows'].append([f'http://amigo.geneontology.org/amigo/term/{go[0]}@{go[0]}']+go[1:])
        else: goList[queryP] = []
        if queryP in homologList:
            for hom in homologList[queryP]:
                jsonwp[f'page:{queryP}']['table:homList']['rows'].append([f'https://www.uniprot.org/uniprot/{hom[0]}@{hom[0]}']+hom[1:5]+
                                                                        [f'{queryP}-{hom[0]}@{hom[5]}'])
                if align: jsonwp[f'page:{queryP}-{hom[0]}'] = createAlignmentPage(queryP,hom[0])
        else: homologList[queryP] = []
        #print(homologList[queryP][0])
        if len(homologList[queryP]) > 0:
            jsonwp['table:proteinList']['rows'].append([f'{queryP}@{queryP}',len(homologList[queryP]),len(goList[queryP]),homologList[queryP][0][0],homologList[queryP][0][5]])
        else:
            jsonwp['table:proteinList']['rows'].append([f'{queryP}@{queryP}',len(homologList[queryP]),len(goList[queryP]),'',''])
        cnt = cnt + 1
        if cnt % 20 == 0:
            size = sys.getsizeof(json.dumps(jsonwp))
            if size >= 33500000:
                break
    # Write the dictionary to a JSON file
    with open(out+'.json', "w") as f:
        json.dump(jsonwp, f)
    return cnt

@click.command()
@click.option('--thr', default=0.05, help='E-value threshold for homolog detection')
@click.option('-n', '--jobs', default=1, help='Number of jobs to run in parallel')
@click.argument('querydb', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('targetdb', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('out', type=click.Path(exists=False,file_okay=True,dir_okay=False))
def search(thr, jobs, querydb, targetdb, out):
    '''Search a query database in target database.
This command searches a query database against a target database.
Both databases should be created using makedb command.
Databases can contain one or more sequences.
An e-value threshold can be specified with --thr flag. The default e-value threshold is 0.05'''
    goList,homologList = _search(thr,None,querydb,targetdb,None,jobs)
    print(f'Saving results into {out}.tsv.')
    toTSV(goList,homologList,out)
    print(f'You can use `prost tojsonwp` command to convert {out}.tsv results into a webpage!')

@click.command()
@click.option('--thr', default=0.05, help='E-value threshold for homolog detection')
@click.option('--gothr', default=0.05, help='E-value threshold for GO annotation')
@click.option('-n', '--jobs', default=1, help='Number of jobs to run in parallel')
@click.argument('querydb', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.argument('out', default='PROST.res', type=click.Path(exists=False,file_okay=True,dir_okay=False))
def searchsp(thr,gothr,jobs, querydb, out):
    '''Search query database in SwissProt February 2023 database.
This command searches a query database against a SwissProt February 2023 database.
Query database should be created using makedb command.
It can contain one or more sequences.
An e-value threshold can be specified with --thr flag. The default e-value threshold is 0.05.
An seperate GO annotation threshold can be specified with --gothr flag. The default is 0.05.'''
    goList,homologList = _search(thr,gothr,querydb,prostdir+'/sp.02.23.parsed.prdb',prostdir+'/sp.02.23.go.pkl',jobs)
    print(f'Saving results into {out}.tsv.')
    toTSV(goList,homologList,out)
    print(f'You can use `prost tojsonwp` command to convert {out}.tsv results into a webpage!')
        
@click.command()
@click.argument('tsv', type=click.Path(exists=True,file_okay=True,dir_okay=False))
@click.option('-a', '--align', is_flag=True, default=False, help='Create alignment pages')
@click.option('-i', '--info', default="", help='Info to include the webpage')
@click.argument('out', default='out.json', type=click.Path(exists=False,file_okay=True,dir_okay=False))
def tojsonwp(tsv, align, info, out):
    '''Covnert search results into webpage using JSONWP tool'''
    goList,homologList = {},{}
    print(f'Read {tsv} file.') 
    with open(tsv,'r') as f:
        for line in f:
            line = line.strip().split('\t')
            if line[1][0:3] == 'GO:':
                if line[0] not in goList: goList[line[0]] = []
                goList[line[0]].append(line[1:])
            else:
                if line[0] not in homologList: homologList[line[0]] = []
                homologList[line[0]].append(line[1:])
    prots = list(homologList.keys())
    lprots = len(prots)
    cur = 0
    i =  0
    while cur < lprots:
        print(f'Create {i+1}.th json file.')
        cur += toJSONWP(None,None,None,None,info,align,goList,homologList,prots[cur:],out+f'.{i}')
        i += 1
    
@click.group()
def cli():
    '''PROST python package v0.2.15
Please specify a command.
makedb: creates a PROST database from given fasta file. The fasta file usually contains more than one entry.
search: searches a query database against a target database. Query database can contain one or more sequences embedded using makedb command.
searchsp: searches a query database against SwissProt February 2023 database. Query database can contain one or more sequences embedded using makedb command.'''
    pass

cli.add_command(makedb)
cli.add_command(mergedbs)
cli.add_command(search)
cli.add_command(searchsp)
cli.add_command(mkgo)
cli.add_command(mkcache)
cli.add_command(parseUniprotNames)
cli.add_command(tojsonwp)

if __name__ == '__main__':
    cli()

