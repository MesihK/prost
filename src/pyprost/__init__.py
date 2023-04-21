def _init_prost_files():
    import os
    import urllib.request
    from pathlib import Path
    import hashlib

    def md5(file):
        # Open the file in binary mode
        with open(file, "rb") as file:
            # Read the contents of the file in chunks
            chunk_size = 1024
            md5sum = hashlib.md5()
            while chunk := file.read(chunk_size):
                md5sum.update(chunk)

        # Get the hexadecimal representation of the MD5 checksum
        return md5sum.hexdigest()

    if 'PROSTDIR' in os.environ: prostdir = os.environ['PROSTDIR']
    else: prostdir = str(Path.home())+'/.config/prost'
    if not os.path.exists(prostdir): os.makedirs(prostdir)

    def download_file(name,info,md5sum,v='v0.2.7'):
        if not os.path.exists(prostdir+'/'+name):
            print(info)
            link=f'https://github.com/MesihK/prost/releases/download/{v}/{name}'
            urllib.request.urlretrieve(link, prostdir+'/'+name)
            if md5(prostdir+'/'+name) == md5sum:
                print("Done.")
            else:
            print("Download error, MD5 missmatch!")

    if not os.path.exists(prostdir+'/traced_esm1b_25_13.pt'):
        download_file('traced_esm1b_25_13.part1','Downloading ESM1b weights part1','c18e325af45d02724400c656a3f0a229')
        download_file('traced_esm1b_25_13.part2','Downloading ESM1b weights part2','4c3939d9454503548af127858cfa8deb')

        print("Merge ESM1b weights")
        with open(prostdir+"/traced_esm1b_25_13.part1", "rb") as output_file1:
            first_half = output_file1.read()
        with open(prostdir+"/traced_esm1b_25_13.part2", "rb") as output_file2:
            second_half = output_file2.read()
        # Concatenate the two halves
        contents = first_half + second_half
        # Write the concatenated contents to a new binary file
        with open(prostdir+"/traced_esm1b_25_13.pt", "wb") as merged_file:
            merged_file.write(contents)
        if md5(prostdir+"/traced_esm1b_25_13.pt") == '97c78528f1d54cb52e346a19b367541c':
            print("Done")
        else:
            print("Merge error, MD5 missmatch!")


    download_file('sp.02.23.parsed.prdb','Downloading SwissProt February 2023 Database','5b0afb3753442b132bbdcf552b34c97c')
    download_file('sp.02.23.go.pkl','Downloading SwissProt February 2023 GO Annotations','e142f46823b2987ee219516b152ac430')
    download_file('cache.pkl','Downloading PROST cache','7bc8a2f843af0cfb4d5af8ef574b7a34')

_init_prost_files()
from .prosttools import quantSeq,prostDistance
