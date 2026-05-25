#!/bin/bash
#SBATCH -p v6_384
#SBATCH -N 1
#SBATCH -n 96
source /public1/soft/modules/module.sh
module purge
module load intel/2022.1
module load mpi/intel/2022.1
mpirun vasp_std
