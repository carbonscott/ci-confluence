DTYPE_MASK = np.uint8 # OR: from psana.detector.UtilsMask import DTYPE_MASK, DTYPE_STATUS

o = det.raw
mask = o._mask_default(dtype=DTYPE_MASK)
mask = o._mask_calib()
mask = o._mask_calib_or_default(dtype=DTYPE_MASK)
mask = o._mask_from_status(status_bits=0xffff, stextra_bits:(1<<64)-1, gain_range_inds=(0,1,2,3,4), dtype=DTYPE_MASK, **kwa)
mask = o._mask_neighbors(mask, rad=9, ptrn='r')
mask = o._mask_edges(width=0, edge_rows=1, edge_cols=1, dtype=DTYPE_MASK, **kwa)
mask = o._mask_center(wcenter=0, center_rows=1, center_cols=1, dtype=DTYPE_MASK, **kwa)
mask = o._mask(status=True, status_bits=0xffff, stextra_bits:(1<<64)-1, gain_range_inds=(0,1,2,3,4),\
               neighbors=False, rad=3, ptrn='r',\
               edges=True, width=0, edge_rows=10, edge_cols=5,\
               center=True, wcenter=0, center_rows=5, center_cols=3,\
               calib=False,\
               umask=None,\
               force_update=False, dtype=DTYPE_MASK)