#!/usr/bin/env sh

rm -rf deb_dist lustmolch.egg-info dist
python3 setup.py --command-packages=stdeb.command bdist_deb