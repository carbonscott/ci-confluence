from psana import DataSource
ds = DataSource(exp='rixx1017523', run=520, dir='/sdf/data/lcls/ds/prj/public01\
/xtc')
myrun = next(ds.runs())
timing = myrun.Detector('timing')
for nevt,evt in enumerate(myrun.events()):
    timestamp = evt.timestamp
    upper = (timestamp&0xffffffff00000000)>>32
    lower = (timestamp&0xffffffff)
    timestamp_ns = upper*1000000000+lower
    print(timestamp_ns,timing.raw.pulseId(evt))
    break