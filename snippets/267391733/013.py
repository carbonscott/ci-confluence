from psana import DataSource
ds = DataSource(exp='rixx43518',run=45,dir='/sdf/data/lcls/ds/prj/public01/xtc')
myrun = next(ds.runs())
motor1 = myrun.Detector('motor1')
motor2 = myrun.Detector('motor2')
step_value = myrun.Detector('step_value')
step_docstring = myrun.Detector('step_docstring')
for step in myrun.steps():
    print(motor1(step),motor2(step),step_value(step),step_docstring(step))
    for evt in step.events():
        pass