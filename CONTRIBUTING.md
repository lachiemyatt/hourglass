# Contributing

Thanks for contributing!

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run the app:

```bash
hourglass
```

## Headless test

Headless mode avoids curses and is safe for CI or terminals without TTY:

```bash
hourglass --headless
```

## Compile check

```bash
python -m compileall hourglass
```
