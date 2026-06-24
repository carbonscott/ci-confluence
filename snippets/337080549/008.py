from psana.detector.UtilsMask import *
m = convert_mask2d_to_ndarray_using_pixel_coord_indexes(mask2d, ix, iy)
m = convert_mask2d_to_ndarray_using_geo(mask2d, geo, **kwargs) # NOTE: kwargs are the same as in geo.get_pixel_coord_indexes(**kwargs)
m = convert_mask2d_to_ndarray_using_geometry_file(mask2d, gfname, **kwargs)