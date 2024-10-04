# B4, Btrfs Backups But Better

B4 is another tool for creating incremental backups using btrfs subvolumes.


## ✨ Features

It comes with the following features:
- Backup remote systems or subvolumes
- Backup subvolumes inside subvolumes recursively
- Restore snapshots by replacing or copying them side by side
- Apply rules which subvolumes to keep and how to restore them
- Apply rules how long to keep the backups and at which density.

## ⚡️ Requirements

- Python 3.12 or higher
- A btrfs partition on the machine you want to backup and your backup destination.
- btrfs-progs

## 🚀 Getting Started

Take a look at the [installation guide](https://denialofsandwich.github.io/b4-backup/install.html) to get started.
Once installed, you might take a look at the [example use cases](https://denialofsandwich.github.io/b4-backup/examples.html) to get a starting point.

## Example

This is just an example to explain the most important features. [More examples can be found here](https://denialofsandwich.github.io/b4-backup/examples.html)

Let's say we want to backup a server with a nextcloud instance on it. The btrfs subvolume we want to backup is `/opt/nextcloud`. This is where we store all nextcloud-related data.

```yaml
backup_targets:
  # This is just a name, we want to give our target
  nextcloud.example.com:
    # The location which we want to backup
    source: ssh://root@nextcloud.example.com/opt/nextcloud
    # The location where we want to store the backups.
    # A local path means, that the backups are stored on the same machine as b4.
    destination: /opt/backups
    # In order to be able to send snapshots incrementally, we need to have at least one parent snapshot on source side.
    # Here we can define how many snapshots we want to keep for which amount of time.
    src_retention:
      auto: # You can create multiple rulesets, to be able to handle manual snapshots differently than automatic ones.
        all: "3" # Keep only 3 snapshots on source side
      manual:
        all: "7days" # Keep all snapshots for 7 days on a manual backup
    # The same applies to the destination side.
    dst_retention:
      auto:
        1day: 1month # Keep daily snapshots for 1 month
        1week: 1year # After that remove as many snapshots to only weekly snapshots remain, which are kept fpr a year
        1month: forever # After a year keep snapshots at a monthly interval forever

timezone: utc
# While using the CLI, these are the targets which are used by default.
default_targets:
  - nextcloud.example.com
```

To actually create a backup, you can use the following command:
```bash
b4 backup
```


## Documentation

[The full documentation can be found here](https://denialofsandwich.github.io/b4-backup/)
