    from psana import DataSource
    ds = DataSource(exp='tmoc00318',run=10, dir='/cds/data/psdm/prj/public01/xtc')
    orun = next(ds.runs())
    det = orun.Detector('epix100', **kwa) # see content of **kwa later