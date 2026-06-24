from psana.detector.mask import Mask, DTYPE_MASK

m = Mask(det,\
         status=True, status_bits=0xffff, stextra_bits:(1<<64)-1, gain_range_inds=(0,1,2,3,4),\
         neighbors=True, rad=5, ptrn='r',\
         edges=True, width=0, edge_rows=10, edge_cols=5,\
         center=True, wcenter=0, center_rows=5, center_cols=3,\
         calib=True,\
         umask=test_umask(det),\
         force_update=False, dtype=DTYPE_MASK)

m = Mask(det) # minimal version.