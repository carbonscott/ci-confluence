# Use environment variable to specify the live-mode timeout,
# set to 30 seconds in this example. This timeout controls two
# behaviors: how long to wait for the files to exist, and how long
# to wait for a file to grow.  psana will exit when the timeout
# time expires.
import os
os.environ['PS_R_MAX_RETRIES'] = '30'

# Optional live-mode performance tuning.
#
# PS_SMD_N_EVENTS controls how many smalldata events psana tries to use
# when forming each SMD batch. Larger values can improve throughput, but
# they also increase live-mode latency because psana may wait longer for
# all streams to reach the batch boundary. Smaller values usually make
# live monitoring start moving sooner.
#
# For live monitoring, common values are 100-1000. For maximum throughput,
# larger values such as 5000-20000 may be better. 
os.environ["PS_SMD_N_EVENTS"] = "1000"

# Create a datasource with live flag
from psana import DataSource
ds = DataSource(exp='tmoc00118', run=222, dir='/sdf/data/lcls/ds/prj/public01/xtc', 
        live        = True,
        max_events  = 10)


# Looping over your run and events as usual
# You'll see "wait for an event..." message in case
# The file system writing is slower than your analysis
run = next(ds.runs())
for i, evt in enumerate(run.events()):
    print(f'got evt={i} ts={evt.timestamp}')