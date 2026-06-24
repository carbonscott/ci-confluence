from psana import DataSource
ds = DataSource(exp='tmoc00118',run=222,dir='/sdf/data/lcls/ds/prj/public01/xtc')
myrun = next(ds.runs())
timing = myrun.Detector('timing')
for nevt,evt in enumerate(myrun.events()):
    allcodes = timing.raw.eventcodes(evt)
    # event code 15 fires at 1Hz, and this exp/run had 10Hz triggers            
    print('event code 15 present:',allcodes[15])
    if nevt>20: break