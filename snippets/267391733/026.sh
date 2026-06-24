#!/bin/bash
#SBATCH --partition=milano
#SBATCH --job-name=run_large_psana2
#SBATCH --output=output-%j.txt
#SBATCH --error=output-%j.txt
#SBATCH --nodes=3
#SBATCH --exclusive
#SBATCH --time=10:00

# Configure psana2 parallelization
source setup_hosts_openmpi.sh

# Run your job with the hostfile flag
mpirun --hostfile $PS_HOST_FILE python test_mpi.py