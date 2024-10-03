# Terminology

## Source Host

The source host is the host where the data is being backed up from. You specify a target location where the data you want to backup is laying. If you run a backup, the data is first incrementally copied to the source snapshot directory and then copied to the destination host.

## Destination Host

The destination host is the host where the data is being backed up to.

## Backup Target

The backup target contains the definition of the backup. It contains the source and destination host, the source and destination path, the retention rulesets, how to restore snapshots and more.

## Retention Ruleset / Retention Name

A retention ruleset is a set of rules that define how long a snapshot should be kept. A retention name is a string that identifies a retention ruleset.

An example of a retention ruleset is the following:

```yaml
auto:
  1day: 2months
  1week: 1year
  1month: forever
```

`auto` is the retention name. The ruleset defines that snapshots that daily snapshots should be kept for 2 months, after that the daily snapshots are deleted in a way, that only weekly snapshots are remaining, which are being kept for one year. After that, only monthly snapshots are kept forever.

## Snapshot

A Snapshot is an incremental recursive point-in-time copy of a btrfs subvolume. Snapshots are created by creating btrfs snapshots from all subvolumes at the target directory. They are stored on source side in the `src_snapshot_dir` and on destination side in the destination directory

## Subvolume

A snapshot can contain multiple btrfs subvolumes, if inside that directory are multiple subvolumes. A subvolume is a separate filesystem tree that can be mounted and accessed independently from the rest of the filesystem in btrfs.

You can define rules for every subvolume inside the target directory for each backup target. This way you can define different retention rules for each subvolume and how to act on a restore, if the subvolumes are already deleted.
