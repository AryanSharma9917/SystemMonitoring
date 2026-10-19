# Original retail recommendation example

This is the original, standalone retail similarity experiment. It does not power
monitoring, alerts, or incident diagnosis. It is retained as an optional example,
separate from the application and its runtime dependencies.

From the repository root:

```bash
uv sync --locked --extra retail
cd examples/retail
../../.venv/bin/python data_prepare.py
```

Run only against trusted local data. The script writes large pickle files into
`data/`; these are ignored by Git. Do not load pickle files from untrusted sources.
The recommendation algorithm remains experimental and is not a supported API.
