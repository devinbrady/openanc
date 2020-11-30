# OpenANC

An open database of Washington, DC Advisory Neighborhood Commission districts, commissioners, and candidates.

[https://openanc.org/](https://openanc.org/)

## Build Process

All live, production website pages are in the `docs/` directory. 

To rebuild all site pages, run: 

```
python build_site.py -riwad
```
Options: 

* `-r` Refresh data. Update local CSVs with data from Google Sheets source. 
* `-i` Build index, map, list, counts, about, and 404 pages. 
* `-w` Build ward pages. 
* `-a` Build ANC pages. 
* `-d` Build district (aka SMD) pages. 