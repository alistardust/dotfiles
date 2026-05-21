# Selective Runs

Use CLI flags to run specific sections or skip others.

```bash
./setup.sh --only zsh vim      # run only these
./setup.sh --skip packages     # skip one, run the rest
./setup.sh --dry-run --only tmux  # preview without changes
./setup.sh --verify --only zsh    # check post-conditions
```
