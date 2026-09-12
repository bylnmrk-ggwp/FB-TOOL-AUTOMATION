# Proofs

Each `*.py` file here is executed by `verify.py` with three globals:
`failures` (append a string to fail the run), `step(name)` (prints a
header), and `ROOT` (project root). Keep one proof file per feature; name
them `NN_feature.py` so they run in order. No pytest here on purpose -
`python verify.py` is the single proof command for this project.
