#!/bin/sh
# install gpodder's missing python deps from the mirror
export DEBIAN_FRONTEND=noninteractive
apt-get update 2>&1 | tail -3
apt-get install -y --force-yes python-feedparser python-conic 2>&1 | tail -5
dpkg -l python-feedparser python-conic | grep ^ii
