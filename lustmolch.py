#!/usr/bin/env python3
import json
import shutil
from collections import namedtuple
from subprocess import run
from pathlib import Path
from jinja2 import Environment, PackageLoader
import click


env = Environment(loader=PackageLoader('lustmolch', 'templates'))
cfg_template = namedtuple('cfg_template', ['source', 'path', 'filename'])

template_files_host = [
    cfg_template('nginx', Path('/etc/nginx/sites-available'), '{name}'),
    cfg_template('80-container-ve.network', Path('/etc/systemd/network'),
        '80-container-ve-{name}.network')
]
nspawn_config = cfg_template('nspawn', Path('/etc/systemd/nspawn'), '{name}.nspawn')
template_files_container = [
    cfg_template('sshd_config', Path('/etc/ssh'), 'sshd_config'),
    cfg_template('80-container-host0.network', Path('/etc/systemd/network'),
        '80-container-host0.network')
]

DEFAULT_TEMPLATE_DIR = '/srv/lustmolch-tools/templates'
DEFAULT_CONF_FILE = '/etc/ssn/lustmolch-containers.json'

FLAVOUR = 'buster'
DEBIAN_MIRROR = 'http://mirror.stusta.de/debian'

SSN_IP_RANGES = ['10.150.0.0/17', '141.84.69.0/24']
www_root = Path('/var/www')

SSH_START_PORT = 10022
SSH_PORT_INCREMENT = 1000

IP_LUSTMOLCH = '141.84.69.235'  # TODO: find out dynamically

IP_START_HOST = (192, 168, 0, 1)
IP_SUBNET_LENGTH = 30


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
    for name, container in cfg.items():
        if container.get('ssh_port') >= port:
            port = container.get('ssh_port') + SSH_PORT_INCREMENT

    return port


def next_ip_address(config_file, name):
    """
    Return the next available (local) IP address to be assigned to the 
    container and the host interfaces.
    Args:
        config_file: Path to container configuration file (containers.json)
        name: Container name

    Returns (tuple): host_ip, container_ip
    """
    if not Path(config_file).exists():
        cfg = {}
    else:
        with open(config_file, 'r') as f:
            cfg = json.load(f)

    if name in cfg:
        return (cfg[name].get('ip_address_host').split('/')[0], 
            cfg[name].get('ip_address_container').split('/')[0])

    ip_host = list(IP_START_HOST)
    for name, container in cfg.items():
        if 'ip_address_host' not in container or 'ip_address_container' not in container:
            continue
        ip_h = container.get('ip_address_host').split('/')[0].split('.')
        if int(ip_h[2]) > ip_host[2]:
            ip_host = [int(x) for x in ip_h]
            ip_host[3] += 4
        elif int(ip_h[2]) == ip_host[2] and int(ip_h[3]) > ip_host[3]:
            if int(ip_h[3]) == 254:
                ip_host[2] += 1
                ip_host[3] = 1
            else:
                ip_host[3] = int(ip_h[3]) + 4
    
    ip_container = list(ip_host)
    ip_container[3] += 1
    return ('.'.join(str(x) for x in ip_host), '.'.join(str(x) for x in ip_container))


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
@click.option('--config-file', default=DEFAULT_CONF_FILE, help='Container configuration file')
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
    ip_address_host, ip_address_container = next_ip_address(config_file, name)
    ssh_port = next_ssh_port(config_file, name)
    context = {
        'name': name,
        'ssh_port': ssh_port,
        'ip_address_host': ip_address_host,
        'ip_address_container': ip_address_container,
        'ip_subnet_length': IP_SUBNET_LENGTH,
        'url': f'{name}.stusta.de'
    }

    click.echo(f'Generated context values for container: {repr(context)}')

    for cfg in template_files_host:
        template = env.get_template('host/' + cfg.source)
        file_name = cfg.path / (cfg.filename.format(**context))
        click.echo(f'Placing config file {file_name}')
        if not dry_run:
            with open(file_name, 'w+') as cfg_file:
                cfg_file.write(template.render(context))

    # create machine
    machine_path = Path('/var/lib/machines', name)
    click.echo('Running debootstrap')
    if not dry_run:
        run(['debootstrap', FLAVOUR, machine_path, DEBIAN_MIRROR], capture_output=True, check=True)

    click.echo('Bootstrapping container')
    if not dry_run:
        # copy and run bootstrap shell script
        script_location = '/opt/bootstrap.sh'
        script_location_host = str(machine_path) + script_location

        shutil.copy(str(Path(DEFAULT_TEMPLATE_DIR, 'container/bootstrap.sh')), script_location_host)
        Path(script_location_host).chmod(0o755)
        run(['systemd-nspawn', '-D', str(machine_path), script_location], check=True)

    click.echo(f'Installing systemd-nspawn config for container {name}')
    if not dry_run:
        template = env.get_template('host/' + nspawn_config.source)
        file_name = nspawn_config.path / (nspawn_config.filename.format(**context))
        with open(file_name, 'w+') as cfg_file:
            cfg_file.write(template.render(context))

    click.echo('Copying config files into container')
    if not dry_run:
        for cfg in template_files_container:
            template = env.get_template('container/' + cfg.source)
            file_name = cfg.filename.format(**context)
            click.echo(f'Placing config file {file_name}')
            if not dry_run:
                with open(Path(f'{machine_path}{cfg.path}/{file_name}'), 'w+') as f:
                    f.write(template.render(context))

    click.echo(f'Updating Iptable rules (filter, nat)')
    if not dry_run:
        for ip_range in SSN_IP_RANGES:
            run(['iptables', '-A', 'INPUT', '-p', 'tcp', '-m', 'tcp',
                '--dport', str(ssh_port), '-s', ip_range, '-j', 'ACCEPT'])
            run(['iptables', '-t' , 'nat', '-A', 'PREROUTING', '-p', 'tcp',
                '-m' ,'tcp', '--dport', str(ssh_port), '-s', ip_range, '-j', 'DNAT',
                '--to-destination', f'{ip_address_container}:22'])
        run(['iptables', '-t', 'nat', '-A', 'POSTROUTING', '-o', f've-{name}',
            '-j', 'SNAT', '--to-source', IP_LUSTMOLCH])

    click.echo('Starting container')
    if not dry_run:
        run(['machinectl', 'start', name], capture_output=True, check=True)

    click.echo('Updating container configuration file')
    if not dry_run:
        update_config(config_file, name, container=context)

    click.echo(f'All done, ssh server running on port {ssh_port}\n'
        'To finish please run "iptables-save".')


@cli.command()
@click.option('--config-file', default=DEFAULT_CONF_FILE, help='Container configuration file')
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
        f.write('\n' + key_string)
    authorized_keys.chmod(0o600)


@cli.command()
@click.option('--dry-run', is_flag=True, default=False)
@click.option('--config-file', default=DEFAULT_CONF_FILE, help='Container configuration file')
@click.argument('name')
def remove_container(dry_run, config_file, name):
    machine_path = Path('/var/lib/machines', name)

    click.echo(f'Stopping container')
    if not dry_run:
        run(['machinectl', 'stop', name], capture_output=True, check=False)

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
    
    click.echo('Removing nspawn config')
    try:
        (nspawn_config.path / nspawn_config.filename.format(name=name)).unlink()
    except OSError as e:
        click.echo(f'{e} ignored when removing nspawn config')

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

    click.echo('All done, although you might need to manually remove some iptable rules.')


if __name__ == '__main__':
    cli()
