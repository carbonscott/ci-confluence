mpirun --mca btl vader,self -n 3 python -m mpi4py.run <myscript>.py
(Gabriel Dorlhiac believes "mpirun --mca pml ob1 --mca btl tcp,sm,self" should work across nodes)