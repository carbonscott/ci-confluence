#!/bin/bash
#SBATCH --partition=milano
#SBATCH --job-name=timestamp_sort_h5
#SBATCH --output=output-%j.txt
#SBATCH --error=output-%j.txt
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --time=10:00

timestamp_sort_h5 /sdf/data/lcls/drpsrcf/ffb/users/monarin/h5/mylargeh5.h5 /sdf/data/lcls/drpsrcf/ffb/users/monarin/h5/output/result.h5

