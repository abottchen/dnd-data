Machine-local symlinks to data repos outside this project. Each machine points `.claude/ext/5etools-src` at its own clone of `5etools-src`. The symlinks themselves are gitignored.

## One-time setup per machine

**Linux / WSL:**
```
ln -s ~/projects/5etools-src .claude/ext/5etools-src
```

**Windows (cmd, no elevation needed — uses a junction):**
```
mklink /J .claude\ext\5etools-src %USERPROFILE%\Documents\Projects\5etools-src
```

Adjust the target path to wherever you actually cloned `5etools-src`.

## How skills use this

Skills that need the data reference it via the `{{DATA_ROOT}}` placeholder. At skill start, Claude runs:

```
(cd .claude/ext/5etools-src && pwd -P)
```

…and substitutes the printed absolute path wherever `{{DATA_ROOT}}` appears in Read/Grep calls. Bash blocks can use the relative path `.claude/ext/5etools-src/...` directly — `$PWD` is the project root.

If the `cd` fails, the symlink is missing; create it per the instructions above.

## Adding a new external repo

1. Add `.claude/ext/<name>` to `.gitignore` (the directory `.claude/ext/` is already a wildcard-gitignored child under the existing entry — check and add if needed).
2. Append an `ln -s` / `mklink /J` example to this README.
3. In new skills, reference `.claude/ext/<name>/...`. If you need Read/Grep support, add a path-resolution preamble (copy from an existing skill and change the symlink name).
