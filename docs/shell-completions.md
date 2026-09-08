# Shell completions

This project ships pre-generated completion scripts for all `otools-*`
commands using native Click 8 shell completion support.

Supported shells:

- bash
- zsh
- fish

The completion files are installed as package data under
`odoo_tools/completions/`.

## Automatic setup (recommended)

After installing `odoo-tools`, run:

```bash
otools-setup shell-completion
```

The command will:

1. Detect your current shell from `$SHELL` (or accept `--shell <bash|zsh|fish>`).
2. Resolve the installed completion directory.
3. Show the exact change it will make to your shell startup file.
4. Write the change only after you confirm.

For **fish** it copies the completion files to `~/.config/fish/completions/`
instead of editing a startup file.

After setup, reload your shell (e.g. `source ~/.bashrc` or open a new terminal).

---

## Manual setup

Follow the steps below if you prefer not to use `otools-setup`.

### Locate the installed completion directory

Run:

```bash
python -c "from importlib.resources import files; print(files('odoo_tools.completions'))"
```

Store it in a variable:

```bash
OTOOLS_COMPLETIONS_DIR="$(python -c "from importlib.resources import files; print(files('odoo_tools.completions'))")"
```

### Bash

Load for current shell:

```bash
for f in "$OTOOLS_COMPLETIONS_DIR"/bash/*; do
  # shellcheck disable=SC1090
  source "$f"
done
```

Persist in `~/.bashrc` by adding the same loop.

### Zsh

Load for current shell:

```zsh
fpath=("$OTOOLS_COMPLETIONS_DIR/zsh" $fpath)
autoload -Uz compinit
compinit
```

Persist by adding these lines to `~/.zshrc`.

### Fish

Install once by copying files to the default fish completions directory:

```bash
mkdir -p ~/.config/fish/completions
cp "$OTOOLS_COMPLETIONS_DIR"/fish/*.fish ~/.config/fish/completions/
```

Open a new fish session (or run `exec fish`).
