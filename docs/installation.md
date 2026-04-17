# Installation

## Requirements

- Python 3.10 or higher
- [Ollama](https://ollama.ai) running locally (or accessible via HTTP)

## Install from Source

```bash
git clone https://github.com/christophevg/yoker.git
cd yoker

# Create virtual environment (recommended)
pyenv virtualenv 3.10.13 yoker
echo "yoker" > .python-version
pyenv activate yoker

# Install
pip install -e ".[dev]"
```

## Verify Installation

```bash
python -m yoker
```

You should see:

```
Yoker v0.1.0
========================================
Yoker v0.1.0 - Using model: glm-5:cloud
Type your message and press Enter. Press Ctrl+D to quit.

>
```

## Install from PyPI

*Planned for future release:*

```bash
pip install yoker
```

## Next Steps

- {doc}`quickstart` - Get started with yoker