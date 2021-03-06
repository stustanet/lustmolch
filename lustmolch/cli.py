import click

from lustmolch.config import DEFAULT_CONF_FILE, init_config
from lustmolch import lustmolch


@click.group()
@click.option(
    '--config-file',
    default=DEFAULT_CONF_FILE,
    help='Container configuration file')
def cli(config_file: str):
    init_config(config_file)


@cli.command()
def list_containers():
    lustmolch.list_containers()


@cli.command()
@click.option('--dry-run', is_flag=True, default=False)
@click.argument('name')
def create_container(dry_run: bool, name: str):
    lustmolch.create_container(dry_run, name)


@cli.command()
@click.option('--key-string', is_flag=True, default=False)
@click.argument('name')
@click.argument('key')
def add_user(key_string: bool, name: str, key: str) -> None:
    lustmolch.add_user(key_string, name, key)


@cli.command()
@click.argument('name')
def remove_user(name: str) -> None:
    lustmolch.remove_user(name)


@cli.command()
@click.option('--dry-run', is_flag=True, default=False)
def update_containers(dry_run: bool) -> None:
    lustmolch.update_containers(dry_run)


@cli.command()
@click.argument('name')
def remove_container(name: str) -> None:
    lustmolch.remove_container(name)
