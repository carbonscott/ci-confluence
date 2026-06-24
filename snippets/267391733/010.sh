Traceback (most recent call last):
  File "/cds/home/m/monarin/lcls2/psana/psana/tests/dummy.py", line 12, in <module>
    ebeam = run.Detector('ebeam')
  File "/cds/home/m/monarin/lcls2/psana/psana/psexp/run.py", line 119, in Detector
    raise DetectorNameError(err_msg)
psana.psexp.run.DetectorNameError: No available detector class matched with ebeam. If this is a new detector/version, make sure to add new class in detector folder.