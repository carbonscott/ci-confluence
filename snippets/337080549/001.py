from psana import DataSource
#ds = DataSource(exp='tmoc00318',run=10, dir='/cds/data/psdm/prj/public01/xtc') # on pcds
ds = DataSource(exp='tmoc00318',run=10, dir='/sdf/data/lcls/ds/prj/public01/xtc')
orun = next(ds.runs())
det = orun.Detector('epix100')
for evt orun.events():
    raw = det.raw.raw()