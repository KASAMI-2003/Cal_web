HTEM gen -k 2,2,2 -encut 400 -mode NVT -in state.in
HTEM create
HTEM strain -ms 0.02 -ns 4 -mthd Stress
HTEM NVT
job_sbatch.sh NVT
HTEM get_results
