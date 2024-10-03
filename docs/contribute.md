# Contribute

Contributions are welcome. If the code quality and tests are sufficient and the PR brings value for the project, I'm ready to accept them.

## Keep the code clean

As we all want to keep the quality of this code high, you should aim for the following:

- Write good tests! Make sure every line of the application code is sufficiently tested.
- Clean code.
- No pipeline errors

## Run tests

If you want to verify your code didn't break anything and test it, you can simply run the unit tests locally.

All tests are located under `/tests`.

### Run all tests

```
pytest
```

## Extend the documentation

The documentation is created using mkdocs and is deployed automatically, if you commit or merge in the master branch.
You can find the documentation at `/docs`.

### Start the development server

You can start and serve the documentation locally, which provides fancy features like hot-reload.
This way you can directly see what you are typing, without the need to push it first.

!!! tip

    The [Code reference][b4_backup.main.b4_backup.B4Backup] pages are generated dynamically by the pipeline.

    To generate these pages yourself run this script:

    ```bash
    poetry run python docs/gen_reference_code.py
    poetry run python docs/gen_reference_config.py
    poetry run typer b4_backup/__main__.py utils docs --name b4 --title "CLI reference" --output docs/reference/cli.md
    ```

Run the development server like this:

```bash
mkdocs serve
```
