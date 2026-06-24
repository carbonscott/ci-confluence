from psana import DataSource
ds = DataSource(exp='tmoc00118', run=222, dir='/sdf/data/lcls/ds/prj/public01/xtc'\
, max_events=100)
myrun = next(ds.runs())
opal = myrun.Detector('tmo_atmopal')
epics_det = myrun.Detector('IM2K4_XrayPower')
for evt in myrun.events():
    img = opal.raw.image(evt)
    epics_val = epics_det(evt) # epics variables have a different syntax
    # check for missing data                                                    
    if img is None:
        print('no image')
    else:
        print(img.shape)
    if epics_val is None:
        print('no epics value')
    else:
        print(epics_val)