#!/usr/bin/env bash

apt-get update
apt-get -y upgrade
apt-get -y install dbus openssh-server vim
systemctl enable systemd-networkd.service
systemctl enable systemd-resolved.service
