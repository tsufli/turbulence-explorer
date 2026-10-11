"""Read workflow inputs from environment, validate, and write the effective config."""
import json
import os
from dataclasses import asdict
from pathlib import Path
from simulation import Config, Solver

config = json.loads(Path('config.json').read_text())
preset = os.environ.get('SIM_PRESET', 'standard') or 'standard'
if preset == 'quick':
    config.update(n=64, kf=8., duration=30., average_after=15.)
elif preset == 'extended':
    config.update(n=256, kf=32., nu=0.00015, duration=200., average_after=100.)
elif preset != 'standard':
    raise ValueError('Unknown preset')
overrides = json.loads(os.environ.get('SIM_OVERRIDES', '{}') or '{}')
if not isinstance(overrides, dict):
    raise ValueError('Overrides must be a JSON object')
config.update(overrides)
c = Config(**config)
if c.duration > 1000 or c.duration / c.dt > 200000:
    raise ValueError('Run exceeds the workflow compute limit; reduce duration or run locally')
if min(c.sample_interval, c.frame_interval) < c.duration / 2000:
    raise ValueError('Limit output to at most 2000 samples/frames')
if c.average_after + c.sample_interval > c.duration:
    raise ValueError('Averaging window must contain at least two samples')
Solver(c)
Path('effective-config.json').write_text(json.dumps(asdict(c), indent=2))
print(json.dumps(asdict(c), indent=2))
