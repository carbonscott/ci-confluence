# Dask array to hdf5 file
import dask.array as da
da_ts = da.from_array([1,2,3], chunks='auto')
da_ts.to_hdf5('out.h5')

# Dask dataframe to hdf5 file
import dask.dataframe as dd
import pandas as pd
d = {'col1': [1, 2, 3, 4], 'col2': [5, 6, 7, 8]}
df = dd.from_pandas(pd.DataFrame(data=d), npartitions=2)
df.to_hdf('/sdf/data/lcls/drpsrcf/ffb/users/monarin/h5/output.hdf', '/data') 