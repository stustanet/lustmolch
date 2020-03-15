import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

DEFAULT_TEMPLATE_DIR = '/srv/lustmolch-tools/templates'
DEFAULT_CONF_FILE = '/etc/ssn/lustmolch-containers.json'

DEFAULTS = {
    'debian_flavour': 'buster',
    'debian_mirror': 'http://mirror.stusta.de/debian',
    'ssn_ip_ranges': ['10.150.0.0/17', '141.84.69.0/24'],
    'www_root': '/var/www',
    'ssh_start_port': 10022,
    'ssh_port_increment': 1000,
    'host_ip': '141.84.69.235',
    'ip_start_host': '192.168.0.1',
    'ip_subnet_length': 30,
    'log_level': logging.INFO
}


class Config:
    def __init__(self, file_path: Path, cfg: Dict[str, Any]):
        self.config = cfg
        self.file_path = file_path

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        if key not in self.config:
            return DEFAULTS[key]

        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> Any:
        self.set(key, value)

    def __delitem__(self, key):
        del self.config[key]

    def save(self):
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

        with self.file_path.open('w+') as f:
            json.dump(self.config, f, indent=2)

    @classmethod
    def from_defaults(cls, file_name: str) -> 'Config':
        cfg: Dict[str, Any] = {
            'users': {},
            'containers': {}
        }

        return cls(Path(file_name), cfg)

    @classmethod
    def from_file(cls, file_name: str) -> 'Config':
        path = Path(file_name)
        if not path.exists():
            logging.info('Config file does not exist, generating defaults')
            return cls.from_defaults(file_name)

        with path.open('r') as f:
            cfg = json.load(f)

        return cls(path, cfg)


config = Config.from_file(DEFAULT_CONF_FILE)


def init_config(config_file: str) -> None:
    global config
    config = Config.from_file(config_file)
