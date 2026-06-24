from psana import DataSource
import numpy as np
import os

# OPTIONAL callback with "gathered" small data from all cores.
# usually used for creating realtime plots when analyzing from
# DAQ shared memory. Called back on each SRV node.
def my_smalldata(data_dict):
    print(data_dict)  

# Event filtering and destination callback (runs on EB cores)
# Use this function to decide if you want to fetch large data for this event  
# and/or direct an event to process on a particular 'rank' 
# (this rank number should be between 1 and total no. of ranks
# (6 for "mpirun -n 6") minus 3 since 3 ranks are reserved for SMD0, EB, SRV
# processes). If a non-epics detector is needed in this routine, make sure to
# add the detector name in small_xtc kwarg for DataSource (see below).
# All epics and scan detectors are available automatically.
def smd_callback(run):
    opal = run.Detector('tmo_opal1')
    epics_det = run.Detector('IM2K4_XrayPower')

    n_bd_nodes = 3 # for mpirun -n 6, 3 ranks are reserved so there are 3 BigData ranks left

    for i_evt, evt in enumerate(run.events()):
        img = opal.raw.image(evt)
        epics_val = epics_det(evt)
        dest = (evt.timestamp % n_bd_nodes) + 1

        if epics_val is not None:
            # Set the destination (rank no.) where this event should be sent to
            evt.set_destination(dest)
            yield evt

# sets the number of h5 files to write. 1 is sufficient for 120Hz operation
# optional: only needed if you are saving h5.
os.environ['PS_SRV_NODES']='1'

ds = DataSource(exp='tmoc00118', run=222, dir='/sdf/data/lcls/ds/prj/public01/xtc',
        max_events  = 40,
        detectors   = ['epicsinfo', 'tmo_opal1', 'ebeam'],  # only reads these detectors (faster)
        smd_callback= smd_callback,                         # event-filtering/destination callback (see notes above)
        small_xtc   = ['tmo_opal1'],                        # detectors to be used in smalldata callback
        )

# batch_size is optional. specifies how often the dictionary of small
# user data is gathered.  if you write out large data (NOT RECOMMENDED) it needs to be set small.
smd = ds.smalldata(filename='mysmallh5.h5', batch_size=5, callbacks=[my_smalldata])

# used for variable-length data example
cnt = 0 
modulus = 4

for run in ds.runs():
    opal = run.Detector('tmo_opal1')
    ebeam = run.Detector('ebeam')

    runsum  = np.zeros((3),dtype=float) # beware of datatypes when summing: can overflow
    for evt in run.events():
        img = opal.raw.image(evt)
        photonEnergy = ebeam.raw.ebeamPhotonEnergy(evt)
        if img is None or photonEnergy is None: continue
        evtsum = np.sum(img)
        # pass either dictionary or kwargs
        smd.event(evt, evtsum=evtsum, photonEnergy=photonEnergy)
        runsum += img[0,:3] # local sum on one mpi core
 
        # an example of variable-length data (must have "var_" name prefix)
        if cnt % modulus:
            x = np.arange(cnt%modulus)
            y = [[x+1, (x+1)**2] for x in range(cnt%modulus)]
            smd.event(evt, {'var_test' : { 'x': x, 'y': y }})
        else:
            # Note, this works either way, either not sending anything or
            # sending 0-length data.  It should be noted if there is *no*
            # data in the entire run, the var_array is *not* written to the
            # output!
            pass
            #smd.event(evt, {'var_test' : { 'x': [], 'y': [] }})
        cnt += 1

    # optional summary data for whole run
    if smd.summary:
        tot_runsum = smd.sum(runsum) # sum (or max/min) across all mpi cores. Must be numpy array or None.
        # pass either dictionary or kwargs
        smd.save_summary({'sum_over_run' : tot_runsum}, summary_int=1)
    smd.done()