"""Entry point for `python -m cotype'.

Exists so `python -m cotype <args>' works alongside the installed
`cotype' console script (registered in `pyproject.toml''s
`[project.scripts]'). Both call into `cotype.cli.main' and exit with
its return value -- there's no other code worth running here.
"""
import sys

from cotype.cli import main

sys.exit(main())
