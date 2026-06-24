from psana import DataSource
import numpy as np
import os

# OPTIONAL callback with "gathered" small data from all cores.
# usually used for creating realtime plots when analyzing from
# DAQ shared memory. Called back on each SRV node.
def my_smalldata(data_dict):
    print(data_dict)

# sets the number of h5 files to write. 1 is sufficient for 120Hz operation
# optional: only needed if you are saving h5.
os.environ['PS_SRV_NODES']='1'

ds = DataSource(exp='tmoc00118', run=222, dir='/sdf/data/lcls/ds/prj/public01/xtc', max_events=10)
# batch_size is optional. specifies how often the dictionary of small
# user data is gathered. if you write out large data (NOT RECOMMENDED) it needs to be set small.
smd = ds.smalldata(filename='mysmallh5.h5', batch_size=5, callbacks=[my_smalldata])

for run in ds.runs():
    opal = run.Detector('tmo_opal1')
    ebeam = run.Detector('ebeam')

    runsum  = np.zeros((3),dtype=float) # beware of datatypes when summing: can overflow
    for i_evt, evt in enumerate(run.events()):
        img = opal.raw.image(evt)
        photonEnergy = ebeam.raw.ebeamPhotonEnergy(evt)
        # important: always check for missing data
        if img is None or photonEnergy is None: continue
        evtsum = np.sum(img)
        # pass either dictionary or kwargs
        smd.event(evt, evtsum=evtsum, photonEnergy=photonEnergy)
        runsum += img[0,:3] # local sum on one mpi core
        # create dataset without padding (e.g. for slow detector) with align_group
        if i_evt % 5 == 0:
            smd.event(evt, slowdata=42, align_group="slow")

    # optional summary data for whole run
    if smd.summary:
        tot_runsum = smd.sum(runsum) # sum (or max/min) across all mpi cores. Must be numpy array or None.
        # pass either dictionary or kwargs.
        smd.save_summary({'sum_over_run' : tot_runsum}, summary_int=1)
    smd.done()