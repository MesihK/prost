## PROST python package v0.2.1

PRotein Ortholog Search Tool is a new homolog detection tool that utilizes ESM-1b language model and iDCT quantization method.
PROST is fast and accurate compared to traditional tools. 

### Installation

The package can be installed via `pip install pyprost`.
On the initial run, PROST will download required files to `~/.config/prost` or an user defined directory via `PROSTDIR` environment variable.

### How to use

Following commands can be used to create databases and perform homology search.

* makedb: creates a PROST database from given fasta file. The fasta file usually contains more than one entry.
* search: searches a query database agains a target database. Query database can contain one or more sequences embedded using makedb command. `--thr` can be used to specify an e-value threshold. The default threshold is 0.05.
* searchsp: searches a query database agains a SwissProt January 2022 database. Query database can contain one or more sequences embedded using makedb command. Again `--thr` can be used to specify an e-value threshold. 

```
prost makedb db/sp.fa db/sp.prdb
prost makedb db/covid.fa db/covid.prdb
prost search --thr 0.05 db/covid.prdb db/sp.prdb results.tsv
prost searchsp --thr 0.05 db/covid.prdb results.tsv
```

