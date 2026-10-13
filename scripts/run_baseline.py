from coach.systems.baseline import run_baseline

report = run_baseline(9041878637)
print(report.model_dump_json(indent=2))