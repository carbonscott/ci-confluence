from psana import DataSource
ds = DataSource(exp='uedcom103',run=796)
myrun = next(ds.runs())
epix = myrun.Detector('epixquad')
print(epix.calibconst)