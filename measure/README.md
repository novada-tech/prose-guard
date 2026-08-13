# measure

The harnesses [CONTRIBUTING.md](../CONTRIBUTING.md) asks you to run. They are not part of the plugin
and nothing at runtime imports them.

| | |
|---|---|
| `measure_check.py` | does a check catch planted defects **and** pass ordinary prose, and how often does it disagree with itself |
| `measure_cost.py` | what a level costs the person using it, against a control in the same run |
| `measure_thresholds.py` | re-derive the author cut and the share threshold on your own audiences |
| `fixtures/well-built/` | ordinary messages every check must pass |

Standard library only, like everything else here. `measure_cost.py` and `measure_check.py` spend real
tokens, which is the point.
