salloc -p ffbgpuq -N 1 --exclusive --gres=gpu:a5000:1
source env.sh
legate --nodes 1 --cpus 1 --gpus 1 --launcher srun <cunumeric script>.py