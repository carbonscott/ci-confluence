# The PS_SMD_N_EVENTS should be set to a small number (e.g. 1)
# since all other events which are part of this intg. event will be sent
# in the same batch.

import os
import numpy as np
os.environ['PS_SMD_N_EVENTS'] = '1'

from psana import DataSource
ds = DataSource(exp='xpptut15', run=1, dir='/sdf/data/lcls/ds/prj/public01/xtc/intg_det',
        intg_det='andor')
run = next(ds.runs())
hsd = run.Detector('hsd')
andor = run.Detector('andor')

# Test calculating sum of the hsd for each integrating event.
sum_hsd = 0
for i_evt, evt in enumerate(run.events()):
    hsd_calib = hsd.raw.calib(evt)
    andor_calib = andor.raw.calib(evt)

    # Keep summing the value of the other detector (hsd in this case)
    sum_hsd += np.sum(hsd_calib[:])/np.prod(hsd_calib.shape)
    
    # When an integrating event is found, print out and reset the sum variable
    if evt.EndOfBatch():
        val_andor = np.sum(andor_calib[:])/np.prod(andor_calib.shape)
        print(f'i_evt: {i_evt} andor: {val_andor} sum_hsd:{sum_hsd}')
        sum_hsd = 0