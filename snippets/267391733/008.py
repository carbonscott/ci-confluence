# Create a datasource and tell it to exclude two detectors
from psana import DataSource
ds = DataSource(exp='tmoc00118', run=222, dir='/sdf/data/lcls/ds/prj/public01/xtc',
        xdetectors  = ['hsd'],      # all other detectors will be available
        max_events  = 10)
 
 
run = next(ds.runs())

# Create these detectors normally 
opal = run.Detector('tmo_opal1')
ebeam = run.Detector('ebeam')
for i, evt in enumerate(run.events()):
    img = opal.raw.image(evt)
    photonEnergy = ebeam.raw.ebeamPhotonEnergy(evt)
    print(f'got evt={i} ts={evt.timestamp} img={img.shape} {photonEnergy=}')