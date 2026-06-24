umask = np.ones((4, 352, 384), dtype=np.uint8)
umask[3,100:120,160:200] = 0

mask = det.raw._mask(status=True, status_bits=0xffff, stextra_bits:(1<<64)-1, gain_range_inds=(0,1,2,3,4),\
                     neighbors=True, rad=5, ptrn='r',\
                     edges=True, edge_rows=10, edge_cols=5,\
                     center=True, center_rows=5, center_cols=3,\
                     calib=False,\
                     umask=umask,\
                     force_update=False, dtype=DTYPE_MASK)
mask += 1 # for visibility of the mask 0 and 1 relative to image background