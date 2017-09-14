#!/usr/bin/env python

from distutils.core import setup

setup(name='nixipfs',
      description='modular NixOS release scripts',
      author='Maximilian Güntner',
      author_email='code@sourcediver.org',
      url='https://github.com/NixIPFS/nixipfs-scripts',
      scripts=['create_channel_release','create_nixipfs','release_nixos','update_binary_cache', 'garbage_collect', 'mirror_tarballs'],
      packages=['nixipfs'],
      package_dir={'nixipfs': 'src'},
      )
