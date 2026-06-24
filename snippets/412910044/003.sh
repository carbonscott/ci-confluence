(ps-4.6.1) python parallel_h5_w_dask_dataframe.py 
RANK:0 client=<Client: 'tcp://172.24.49.11:41253' processes=0 threads=0, memory=0 B>
RANK:0 reading took 0.01s.
RANK:0 inds.size=1000000000 (8000.00MB) ts_chunks=(100000000,) n_procs=10 sorting took 36.83s.
2023-12-08 12:21:04,015 - distributed.protocol.pickle - ERROR - Failed to serialize <ToPickle: HighLevelGraph with 1 layers.
<dask.highlevelgraph.HighLevelGraph object at 0x7f81846c5e50>
 0. 140194150389696
>.
Traceback (most recent call last):
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/pickle.py", line 63, in dumps
    result = pickle.dumps(x, **dump_kwargs)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/h5py/_hl/base.py", line 368, in __getnewargs__
    raise TypeError("h5py objects cannot be pickled")
TypeError: h5py objects cannot be pickled

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/pickle.py", line 68, in dumps
    pickler.dump(x)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/pickle.py", line 29, in reducer_override
    return deserialize, serialize(obj)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/h5py.py", line 24, in serialize_h5py_dataset
    header, _ = serialize_h5py_file(x.file)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/h5py.py", line 11, in serialize_h5py_file
    raise ValueError("Can only serialize read-only h5py files")
ValueError: Can only serialize read-only h5py files

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/pickle.py", line 81, in dumps
    result = cloudpickle.dumps(x, **dump_kwargs)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/cloudpickle/cloudpickle_fast.py", line 73, in dumps
    cp.dump(obj)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/cloudpickle/cloudpickle_fast.py", line 632, in dump
    return Pickler.dump(self, obj)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/h5py/_hl/base.py", line 368, in __getnewargs__
    raise TypeError("h5py objects cannot be pickled")
TypeError: h5py objects cannot be pickled
Traceback (most recent call last):
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/pickle.py", line 63, in dumps
    result = pickle.dumps(x, **dump_kwargs)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/h5py/_hl/base.py", line 368, in __getnewargs__
    raise TypeError("h5py objects cannot be pickled")
TypeError: h5py objects cannot be pickled

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/pickle.py", line 68, in dumps
    pickler.dump(x)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/pickle.py", line 29, in reducer_override
    return deserialize, serialize(obj)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/h5py.py", line 24, in serialize_h5py_dataset
    header, _ = serialize_h5py_file(x.file)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/h5py.py", line 11, in serialize_h5py_file
    raise ValueError("Can only serialize read-only h5py files")
ValueError: Can only serialize read-only h5py files

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/serialize.py", line 350, in serialize
    header, frames = dumps(x, context=context) if wants_context else dumps(x)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/serialize.py", line 73, in pickle_dumps
    frames[0] = pickle.dumps(
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/pickle.py", line 81, in dumps
    result = cloudpickle.dumps(x, **dump_kwargs)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/cloudpickle/cloudpickle_fast.py", line 73, in dumps
    cp.dump(obj)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/cloudpickle/cloudpickle_fast.py", line 632, in dump
    return Pickler.dump(self, obj)
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/h5py/_hl/base.py", line 368, in __getnewargs__
    raise TypeError("h5py objects cannot be pickled")
TypeError: h5py objects cannot be pickled

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/sdf/home/m/monarin/divelite/dask/parallel_h5_w_dask_dataframe.py", line 62, in <module>
    sorted_calib.to_hdf5('/sdf/data/lcls/drpsrcf/ffb/users/monarin/h5/out.h5', '/calib')
  File "/sdf/group/lcls/ds/ana/sw/conda2/inst/envs/ps-4.6.1/lib/python3.9/site-packages/distributed/protocol/serialize.py", line 372, in serialize
    raise TypeError(msg, str(x)[:10000]) from exc
TypeError: ('Could not serialize object of type HighLevelGraph', '<ToPickle: HighLevelGraph with 1 layers.\n<dask.highlevelgraph.HighLevelGraph object at 0x7f81846c5e50>\n 0. 140194150389696\n>')

