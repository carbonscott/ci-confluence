source /cds/sw/ds/ana/conda2-v2/inst/etc/profile.d/conda.sh                                                            
export CONDA_ENVS_DIRS=/cds/sw/ds/ana/conda2/inst/envs/                                                                
export CONDA_PKGS_DIRS=/cds/sw/package/conda_envs/cunumeric-23.07.00/.pkgs

conda activate  /cds/sw/package/conda_envs/cunumeric-23.07.00
export LD_LIBRARY_PATH=/cds/sw/package/conda_envs/cunumeric-23.07.00/lib64:$LD_LIBRARY_PATH