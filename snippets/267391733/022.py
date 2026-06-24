import datetime as dt
from psana import DataSource
ds = DataSource(exp='tmoc00118', run=222, dir='/sdf/data/lcls/ds/prj/public01/xtc')
myrun = next(ds.runs())
for nevt,evt in enumerate(myrun.events()):
    if nevt>3: break
    t = evt.datetime()
    localt = t.replace(tzinfo=dt.timezone.utc).astimezone(tz=None)    
    print(localt.strftime('%H:%M:%S'))