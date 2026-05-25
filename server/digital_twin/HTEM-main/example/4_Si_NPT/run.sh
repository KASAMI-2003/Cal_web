HTEM gen -k 2,2,2 -e 400 -T 600,1200,2 -P 8 -mode NPT
HTEM create
HTEM strain -ms 0.03 -mthd Stress
HTEM NPT
job_sbatch.sh NPT
HTEM update -up NPT
HTEM get_results
