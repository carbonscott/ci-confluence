from psana.pscalib.geometry.GeometryAccess import GeometryAccess, img_from_pixel_arrays
geo = GeometryAccess(<geometry-file-name>)
ix, iy = geo.get_pixel_coord_indexes(**kwargs)
mask_nda = geo.get_pixel_mask(mbits=0xffff) # returns mask associated with segment geometry
mask2d = img_from_pixel_arrays(ix, iy, W=mask_nda)

# similar methods are available in the detector interface.
# modify mask2d - add ROI mask bad pixels/regions with mask editor or programatically.