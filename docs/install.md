## Install B4 Backup

### Preconditions

You need the following to be able to use B4 Backup properly:

- Python 3.12 or higher
- A btrfs partition on the machine you want to backup and your backup destination.
- btrfs-progs

=== "Ubuntu, Debian"

    ```bash
    sudo apt install btrfs-progs
    ```

=== "Fedora, Red Hat"

    ```bash
    sudo yum install btrfs-progs
    ```

### Using pipx (recommended for users)

1. Install pipx

=== "Ubuntu, Debian"

    ```bash
    sudo apt install pipx
    ```

=== "Fedora, Red Hat"

    ```bash
    sudo yum install pipx
    ```

2. Install B4 Backup (Fill in token and name)

    ```bash
    pipx install b4-backup
    ```

3. Next steps

    - [Examples][examples]
    - [CLI reference][cli-reference]
    - [Config reference][configuration]

### Using poetry (for developers)

1. [Install poetry](https://python-poetry.org/docs/#installation)

2. [Clone the repository](https://github.com/denialofsandwich/b4-backup)

3. Setup poetry environment:

    ```bash
    cd <path_to_repo>
    ```

    Finally, install the package with poetry:

    ```bash
    poetry install
    ```

4. Next steps

    Just switch into the poetry environment using `poetry shell`.

    - [Examples][examples]
    - [CLI reference][cli-reference]
    - [Config reference][configuration]

## Update B4 Backup

### Using pipx

Similar to the installation, you upgrade B4 Backup like this:

```bash
pipx upgrade b4-backup
```

### Using poetry

```bash
cd <path_to_repo>
git pull
poetry install
```

## Uninstall B4 Backup

### Using pipx

```bash
pipx uninstall b4-backup
```

### Using poetry

It's technically never installed, but you can remove it like that:

```bash
cd <path_to_repo>
poetry env list
# Delete every environment using
poetry env remove <env_name>
cd ..
rm -rf b4_backup
```
