#!/bin/sh
# Build the Harmattan deb of this tree on the arch box inside an Ubuntu 20.04
# container (the last Ubuntu with python2 + debhelper + intltool; Debian
# bullseye's security pool is already gone from the mirrors).
#
#   tools/harmattan-tls/build-deb.sh            -> gpodder_<version>_all.deb in the tree root
#
# The tree is synced to arch:/dev/shm/gpodder-build (arch's /tmp quota is small),
# dpkg-buildpackage runs with -d (build-deps are only needed on the device).
set -e
HERE=$(cd "$(dirname "$0")/../.." && pwd)
VER=$(head -1 "$HERE/debian/changelog" | sed 's/.*(\(.*\)).*/\1/')
ssh arch 'rm -rf /dev/shm/gpodder-build && mkdir -p /dev/shm/gpodder-build'
rsync -a --delete -e ssh --exclude .git "$HERE/" arch:/dev/shm/gpodder-build/gpodder/
ssh arch 'docker run --rm -v /dev/shm/gpodder-build:/w -w /w/gpodder -e DEBIAN_FRONTEND=noninteractive ubuntu:20.04 sh -c "
  apt-get update -qq >/dev/null 2>&1
  apt-get install -y --no-install-recommends python2.7 python-is-python2 debhelper intltool gettext fakeroot >/dev/null 2>&1
  dpkg-buildpackage -us -uc -b -d 2>&1 | tail -3"'
scp -q "arch:/dev/shm/gpodder-build/gpodder_${VER}_all.deb" "$HERE/"
ls -la "$HERE/gpodder_${VER}_all.deb"
echo "install on the device:  sudo apt-get install python-feedparser python-conic"
echo "                        sudo aegis-dpkg -i gpodder_${VER}_all.deb"
