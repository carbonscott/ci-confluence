(ps-4.6.1) python parallel_h5_w_dask_dataframe.py 
RANK:0 client=<Client: 'tcp://172.24.49.11:41613' processes=0 threads=0, memory=0 B>
RANK:0 reading took 0.01s.
RANK:0 inds.size=1000000000 (8000.00MB) ts_chunks=(1000000000,) n_procs=1 sorting took 32.17s.

(ps-4.6.1) python parallel_h5_w_dask_dataframe.py 
RANK:0 client=<Client: 'tcp://172.24.49.11:43255' processes=0 threads=0, memory=0 B>
RANK:0 reading took 0.01s.
RANK:0 inds.size=1000000000 (8000.00MB) ts_chunks=(100000000,) n_procs=10 sorting took 39.50s.