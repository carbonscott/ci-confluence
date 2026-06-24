from psana import DataSource
import os
import numpy as np
os.environ['PS_SMD_N_EVENTS'] = '50'
os.environ['PS_SRV_NODES']='1'

ds = DataSource(exp='rixx1003721', run=161, intg_det='epixhr')
smd = ds.smalldata(filename='phil.h5')
myrun = next(ds.runs())
epix = myrun.Detector('epixhr')
step_avgs = {}
for nstep,step in enumerate(myrun.steps()):
    print('step',nstep)
    localsum = None
    nsum = 0
    for nevt,evt in enumerate(step.events()):
        # convert from uint16 to uint32 so we don't overflow the sum
        raw = epix.raw.raw(evt).astype(np.uint32)
        if raw is not None:
            nsum+=1
            if localsum is None:
                localsum = raw
            else:
                localsum += raw
    step_sum = smd.sum(localsum)
    step_nsum = smd.sum(nsum)
    # check if we are the one mpi rank that sees the sums
    if step_sum is not None:
        step_avgs[str(nstep)] = step_sum/step_nsum
if smd.summary:
    smd.save_summary(step_avgs)
smd.done()