HTEM gen -k 2,2,2 -e 400 -s 0.2 -T 0 -P 0,10,11 -mode cold
HTEM create
job_sbatch.sh relax1
HTEM strain -ms 0.02 -ns 8 -mthd Stress
HTEM relax2
job_sbatch.sh relax2
HTEM static
job_sbatch.sh static
HTEM update -up CONTCAR
HTEM get_results
