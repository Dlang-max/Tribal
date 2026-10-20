# Tribal
## Letting agents learns for other agents

1. Define a standard for strucutre the markdown files that agent write and add to the knowledge base
2. Define the schema for storing the knowledge graph in MySQL
3.

## Python Markdown validator

See the [installation and usage guide](docs/parser_usage.md) and [public Python API](docs/parser_api.md).

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
tribal validate fixtures/markdown_v1/baseline --json
python -m pytest --cov=tribal --cov-branch
```
