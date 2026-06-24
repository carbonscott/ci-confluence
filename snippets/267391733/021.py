from psana import DataSource
from mpi4py import MPI
import numpy as np

ds = DataSource(exp='tmoc00118', run=222,
                dir='/sdf/data/lcls/ds/prj/public01/xtc')
myrun = next(ds.runs())
opal = myrun.Detector('tmo_atmopal')
ts_list = [4194783241933859761, 4194783249723600225,
           4194783254218190609, 4194783258712780993]

with myrun.build_table() as success:
    if success:
        for i, ts in enumerate(ts_list):
            evt = myrun.event(ts)
            img = opal.raw.image(evt)
            print(i, ts, img.shape)