#!/usr/bin/env python3
import json
import shutil
from collections import namedtuple
from subprocess import run
from pathlib import Path
from jinja2 import Environment, PackageLoader
import click


env = Environment(loader=PackageLoader('lustmolch', 'container'))
cfg_template = namedtuple('cfg_template', ['source', 'path', 'filename'])

template_files_host = [
    cfg_template('nginx', Path('/etc/nginx/sites-available'), '{name}'),
    cfg_template('nspawn', Path('/etc/systemd/nspawn'), '{name}.nspawn')
]
template_files_container = [
    cfg_template('sshd_config', Path('/etc/ssh'), 'sshd_config')
]

FLAVOUR = 'buster'
DEBIAN_MIRROR = 'http://mirror.stusta.de/debian'

www_root = Path('/var/www')

SSH_START_PORT = 10022
SSH_PORT_INCREMENT = 1000


def next_ssh_port(config_file, name):
    """
    Return the next available port for the containers ssh server to run on.
    If the container is already present in the list of installed containers
    returns the configured port.
    Args:
        config_file: Path to container configuration file (containers.json)
        name: Container name

    Returns: SSH port

    """
    if not Path(config_file).exists():
        cfg = {}
    else:
        with open(config_file, 'r') as f:
            cfg = json.load(f)

    if name in cfg:
        return cfg.get(name).get('ssh_port')
    port = SSH_START_PORT
    for container in cfg.items():
        if container.get('ssh_port') >= port:
            port = container.get('ssh_port') + SSH_PORT_INCREMENT

    return port


def update_config(config_file, name, container):
    if not Path(config_file).exists():
        with open(config_file, 'w+') as f:
            cfg = {name: container}
            json.dump(cfg, f, indent=4)
    else:
        with open(config_file, 'r') as f:
            cfg = json.load(f)
            cfg[name] = container
        with open(config_file, 'w') as f:
            json.dump(cfg, f, indent=4)


@click.group()
def cli():
    pass


@cli.command()
@click.option('--dry-run', is_flag=True, default=False)
@click.option('--config-file', default='containers.json', help='Container configuration file')
@click.argument('name')
def create_container(dry_run, config_file, name):
    if dry_run:
        click.echo(f'Doing a dry run')

    # create shared folder for html static files
    www_dir = www_root / name
    click.echo(f'Creating shared www directory "{www_dir}"')
    if not dry_run:
        www_dir.mkdir(parents=True, exist_ok=True)

    # place configuration files
    context = {
        'name': name,
        'ssh_port': next_ssh_port(config_file, name)
    }
    for cfg in template_files_host:
        template = env.get_template(cfg.source)
        file_name = cfg.path / (cfg.filename.format(**context))
        click.echo(f'Placing config file {file_name}')
        if not dry_run:
            with open(file_name, 'w+') as cfg_file:
                cfg_file.write(template.render(context))

    # create machine
    machine_path = Path('/var/lib/machines', name)
    click.echo(f'Running debootstrap')
    if not dry_run:
        run(['debootstrap', FLAVOUR, machine_path, DEBIAN_MIRROR], capture_output=True, check=True)

    # start container for the first time
    # click.echo(f'Starting container for the first time')
    # if not dry_run:
    #     run(['systemd-nspawn', '-D', machine_path], check=True)

    click.echo(f'Bootstrapping container')
    if not dry_run:
        # copy and run bootstrap shell script
        script_location = '/opt/bootstrap.sh'
        script_location_host = str(machine_path) + script_location

        shutil.copy('container/bootstrap.sh', script_location_host)
        Path(script_location_host).chmod(0o755)
        run(['systemd-nspawn', '-D', str(machine_path), script_location], check=True)

    click.echo(f'Copying config files into container')
    if not dry_run:
        for cfg in template_files_container:
            template = env.get_template(cfg.source)
            file_name = cfg.filename.format(**context)
            click.echo(f'Placing config file {file_name}')
            if not dry_run:
                with open(Path(f'{machine_path}{cfg.path}/{file_name}'), 'w+') as f:
                    f.write(template.render(context))

    click.echo(f'Starting container')
    if not dry_run:
        run(['machinectl', 'start', name], capture_output=True, check=True)

    click.echo(f'Updating container configuration file')
    if not dry_run:
        update_config(config_file, name, container=context)

    click.echo(f'All done, ssh server running on port {context["ssh_port"]}')


@cli.command()
@click.option('--config-file', default='containers.json', help='Container configuration file')
@click.option('--key-string', is_flag=True, default=False)
@click.argument('name')
@click.argument('key')
def install_ssh_key(config_file, key_string, name, key):
    ssh_dir = Path('/var/lib/machines', name, 'root/.ssh')
    authorized_keys = ssh_dir / 'authorized_keys'
    if key_string:
        key_string = key
    else:
        with open(key, 'r') as f:
            key_string = f.read()

    click.echo(f'Appending ssh key\n{key_string} to {authorized_keys}')
    ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(authorized_keys, 'a+') as f:
        f.write(key_string)
    authorized_keys.chmod(0o600)


@cli.command()
@click.option('--config-file', default='containers.json', help='Container configuration file')
@click.argument('name')
def remove_container(config_file, name):
    machine_path = Path('/var/lib/machines', name)

    # removing shared folder
    www_dir = www_root / name
    click.echo(f'Removing shared www folder')
    try:
        shutil.rmtree(www_dir, ignore_errors=True)
    except OSError as e:
        click.echo(f'{e} ignored when removing container')

    # deleting placed config files
    for cfg in template_files_host:
        file_name = cfg.path / cfg.filename.format(name=name)
        click.echo(f'Removing config file {file_name}')
        try:
            file_name.unlink()
        except OSError as e:
            click.echo(f'{e} ignored when removing file {file_name}')

    # delete container itself
    click.echo(f'Removing container')
    try:
        shutil.rmtree(machine_path, ignore_errors=True)
    except OSError as e:
        click.echo(f'{e} ignored when removing container')

    # remove container from configuration file
    click.echo(f'Updating configuration file')
    try:
        with open(config_file, 'r') as f:
            cfg = json.load(f)
            if name in cfg:
                del cfg[name]
                with open(config_file, 'w') as f:
                    json.dump(cfg, f, indent=4)
    except OSError as e:
        click.echo(f'{e} ignored when updating config file')


if __name__ == '__main__':
    cli()
