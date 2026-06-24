from psana.detector.mask import Mask, DTYPE_MASK

kwa = {'status':True, 'status_bits':0xffff, 'stextra_bits':(1<<64)-1, 'gain_range_inds':(0,1,2,3,4),\
       'neighbors':False, 'rad':3, 'ptrn':'r',\
       'edges':False, 'width':0, 'edge_rows':10, 'edge_cols':5,\
       'center':False, 'wcenter':0, 'center_rows':5, 'center_cols':3,\
       'calib':False,\
       'umask':None,\
       'force_update':False, 'dtype':DTYPE_MASK}

m = Mask(det, **kwa)

m = Mask(det) # minimal version for default mask parameters.