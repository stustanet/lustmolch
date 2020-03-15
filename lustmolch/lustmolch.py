import json
import logging
import shutil
from collections import namedtuple
from pathlib import Path
from subprocess import run
from typing import Tuple

from jinja2 import Environment, PackageLoader

from .config import config, DEFAULT_TEMPLATE_DIR

logging.basicConfig(format='%(levelname)s:%(message)s', level=config['log_level'])

env = Environment(loader=PackageLoader('lustmolch',  'templates'))
cfg_template = namedtuple('cfg_template', ['source', 'path', 'filename'])

template_files_host = [
    cfg_template('nginx', Path('/etc/nginx/sites-available'), '{name}'),
    cfg_template('80-container-ve.network', Path('/etc/systemd/network'),
                 '80-container-ve-{name}.network')
]
template_files_container = [
    cfg_template('sshd_config', Path('/etc/ssh'), 'sshd_config'),
    cfg_template('80-container-host0.network', Path('/etc/systemd/network'),
                 '80-container-host0.network')
]
nspawn_config = cfg_template('nspawn', Path(
    '/etc/systemd/nspawn'), '{name}.nspawn')


def next_ssh_port(name: str) -> int:
    """
    Return the next available port for the containers ssh server to run on.
    If the container is already present in the list of installed containers
    returns the configured port.
    Args:
        name: Container name

    Returns: SSH port
    """

    if name in config['containers']:
        return config['containers'][name].get('ssh_port')

    port = config['ssh_start_port']
    for container in config['containers'].values():
        if container['ssh_port'] >= port:
            port = container['ssh_port'] + config['ssh_port_increment']

    return port


def next_ip_address(name: str) -> Tuple[str, str]:
    """
    Return the next available (local) IP address to be assigned to the
    container and the host interfaces.
    Args:
        name: Container name

    Returns (tuple): host_ip, container_ip
    """

    if name in config['containers']:
        c = config['containers'][name]
        return (c.get('ip_address_host').split('/')[0],
                c.get('ip_address_container').split('/')[0])

    ip_host = [int(ip) for ip in config['ip_start_host'].split('.')]

    container_ips = [container['ip_address_host'].split('/')[0].split('.')
                     for container in config['containers'].values()]

    ip_host[2] = max([int(ip[2]) for ip in container_ips] + [ip_host[2]])
    ip_host[3] = max([int(ip[3]) for ip in container_ips] + [ip_host[3]])
    ip_host[3] += 4

    if ip_host[3] >= 254:
        ip_host[3] = 1
        ip_host[2] += 1
    if ip_host[2] == 254:
        logging.error('Error no available IP addresses found')
        raise Exception()

    ip_container = list(ip_host)
    ip_container[3] += 1
    return (
        '.'.join(str(x) for x in ip_host),
        '.'.join(str(x) for x in ip_container)
    )


def list_containers():
    """output lustmolch configuration file"""
    # TODO: make nice

    print('Currently registered containers:\n')
    print(json.dumps(config.config, indent=2))


def create_container(dry_run, name):
    """Creates a systemd-nspawn container."""
    if dry_run:
        logging.info(f'Doing a dry run')

    # create shared folder for html static files
    www_dir = Path(config['www_root']) / name
    logging.info(f'Creating shared www directory "{www_dir}"')
    if not dry_run:
        www_dir.mkdir(parents=True, exist_ok=True)

    # place configuration files
    ip_address_host, ip_address_container = next_ip_address(name)
    ssh_port = next_ssh_port(name)
    context = {
        'name': name,
        'ssh_port': ssh_port,
        'ip_address_host': ip_address_host,
        'ip_address_container': ip_address_container,
        'ip_subnet_length': config['ip_subnet_length'],
        'url': f'{name}.stusta.de',
        'users': []
    }

    logging.info(f'Generated context values for container: {repr(context)}')

    for cfg in template_files_host:
        template = env.get_template('host/' + cfg.source)
        file_name = cfg.path / (cfg.filename.format(**context))
        logging.info(f'Placing config file {file_name}')
        if not dry_run:
            with open(file_name, 'w+') as cfg_file:
                cfg_file.write(template.render(context))

    # create machine
    machine_path = Path('/var/lib/machines', name)
    logging.info('Running debootstrap')
    if not dry_run:
        run(['debootstrap', config['debian_flavour'], machine_path, config['debian_mirror']],
            capture_output=True, check=True)

    logging.info('Bootstrapping container')
    if not dry_run:
        # copy and run bootstrap shell script
        script_location = '/opt/bootstrap.sh'
        script_location_host = str(machine_path) + script_location

        shutil.copy(
            str(Path(DEFAULT_TEMPLATE_DIR, 'container/bootstrap.sh')),
            script_location_host)
        Path(script_location_host).chmod(0o755)
        run(['systemd-nspawn', '-D', str(machine_path), script_location],
            check=True)

    logging.info(f'Installing systemd-nspawn config for container {name}')
    if not dry_run:
        template = env.get_template('host/' + nspawn_config.source)
        file_name = nspawn_config.path / (nspawn_config.filename.format(**context))
        with open(file_name, 'w+') as cfg_file:
            cfg_file.write(template.render(context))

    logging.info('Copying config files into container')
    if not dry_run:
        for cfg in template_files_container:
            template = env.get_template('container/' + cfg.source)
            file_name = cfg.filename.format(**context)
            logging.info(f'Placing config file {file_name}')
            if not dry_run:
                with open(Path(f'{machine_path}{cfg.path}/{file_name}'), 'w+') as f:
                    f.write(template.render(context))

    logging.info(f'Updating Iptable rules (filter, nat)')
    if not dry_run:
        for ip_range in config['ssn_ip_ranges']:
            run(['iptables', '-A', 'INPUT', '-p', 'tcp', '-m', 'tcp',
                 '--dport', str(ssh_port), '-s', ip_range, '-j', 'ACCEPT'])
            run(['iptables', '-t', 'nat', '-A', 'PREROUTING', '-p', 'tcp',
                 '-m', 'tcp', '--dport', str(
                    ssh_port), '-s', ip_range, '-j', 'DNAT',
                 '--to-destination', f'{ip_address_container}:22'])
        run(['iptables', '-t', 'nat', '-A', 'POSTROUTING', '-o', f've-{name}',
             '-j', 'SNAT', '--to-source', config['host_ip']])

    logging.info('Starting container')
    if not dry_run:
        run(['machinectl', 'start', name], capture_output=True, check=True)

    logging.info('Updating container configuration file')
    if not dry_run:
        config['containers'][name] = context
        config.save()

    logging.info(f'All done, ssh server running on port {ssh_port}\n'
                 'To finish please run "iptables-save".')


def add_user(key_string: bool, name: str, key: str) -> None:
    """add user to lustmolch management"""
    if not key_string:
        with open(key, 'r') as f:
            key = f.read()

    config['users'][name] = {
        'name': name,
        'key': key
    }

    config.save()


def remove_user(name: str) -> None:
    """remove a user, doesn't remove the user from all containers"""
    logging.info(f'Removing user {name}')
    if name in config['users']:
        del config['users'][name]

    for container in config['containers']:
        container['users'] = [user for user in container['users'] if user != name]

    config.save()


def update_containers(dry_run: bool) -> None:
    """update users on all containers"""

    for container in config['containers'].values():
        ssh_dir = Path('/var/lib/machines', container['name'], 'root/.ssh')
        authorized_keys = ssh_dir / 'authorized_keys'

        keys = [user['key'] for user in config['users'].values() if user['name'] in container['users']]
        keys = '\n'.join(keys)

        logging.info(f'Writing\n{keys}\n to authorized key file {authorized_keys}')
        if not dry_run:
            ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            authorized_keys.touch(mode=0o600, exist_ok=True)
            authorized_keys.write_text(keys)


def remove_container(name: str) -> None:
    """delete a container and its configuration files"""
    machine_path = Path('/var/lib/machines', name)

    logging.info(f'Stopping container')
    run(['machinectl', 'stop', name], capture_output=True, check=False)

    # removing shared folder
    www_dir = Path(config['www_root']) / name
    logging.info(f'Removing shared www folder')
    try:
        shutil.rmtree(www_dir, ignore_errors=True)
    except OSError as e:
        logging.warning(f'{e} ignored when removing container')

    # deleting placed config files
    for cfg in template_files_host:
        file_name = cfg.path / cfg.filename.format(name=name)
        logging.info(f'Removing config file {file_name}')
        try:
            file_name.unlink()
        except OSError as e:
            logging.warning(f'{e} ignored when removing file {file_name}')

    logging.info('Removing nspawn config')
    try:
        (nspawn_config.path / nspawn_config.filename.format(name=name)).unlink()
    except OSError as e:
        logging.warning(f'{e} ignored when removing nspawn config')

    # delete container itself
    logging.info(f'Removing container')
    try:
        shutil.rmtree(machine_path, ignore_errors=True)
    except OSError as e:
        logging.warning(f'{e} ignored when removing container')

    # remove container from configuration file
    logging.info(f'Updating configuration file')
    del config['containers'][name]
    config.save()

    logging.info('All done, although you might need to manually remove some iptable rules.')
