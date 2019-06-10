#!/usr/bin/env bash

apt-get update
apt-get -y upgrade
apt-get -y install dbus openssh-server vim systemd-networkd
systemctl enable systemd-networkd.service