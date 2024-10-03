# Configuration

B4 Backup got a configuration YAML file, where you can override specific parameters as you like.
The default configuration path is `~/.config/b4_backup.yml`.

A full reference of all possible settings and their default values can be found in the [code reference][b4_backup.config_schema.BaseConfig].

```yaml title="Example configuration based on default values"
--8<-- "docs/reference/config.yml"
```

!!! tip

    B4 Backup is using [OmegaConf](https://omegaconf.readthedocs.io/en/latest/) to parse config files.
    OmegaConf also supports variables and resolvers. With resolvers it is possible to insert for example environment variables.<br/>
    A list of all built-in resolvers can be found [here](https://omegaconf.readthedocs.io/en/2.2_branch/custom_resolvers.html#built-in-resolvers).
    B4 Backup implements some resolvers too. [You can find them here][b4_backup.utils.resolve_from_file].
