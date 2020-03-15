from setuptools import setup

VERSION = '1.0.1'
AUTHOR = 'Michael Loipführer'


def readme():
    with open('README.md') as f:
        return f.read()


setup(
    name='lustmolch',
    version=VERSION,
    description='Lustmolch systemd nspwan container utilities',
    long_description=readme(),
    url='http://gitlab.stusta.de/stustanet/lustmolch',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7',
        'Operating System :: POSIX :: Linux'
    ],
    author=AUTHOR,
    author_email='ml@stusta.de',
    install_requires=[
        'Click',
        'jinja2'
    ],
    license='MIT',
    packages=['lustmolch'],
    entry_points={
        'console_scripts': ['lustmolch=lustmolch.cli:cli']
    },
    include_package_data=True,
    zip_safe=False
)
