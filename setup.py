#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

from appdaemon.utils import (__version__)

#sudo apt-get install python3-aiohttp-dbg

REQUIRES = [
    'daemonize',
    'astral',
    'pytz',
    'requests>=2.6.0',
    'sseclient',
    'websocket-client',
    #'aiohttp==3.6.0',
    'aiohttp==3.4.4',
    'yarl==1.1.0',
    'Jinja2==2.10.1',
    'aiohttp_jinja2==0.15.0',
    'pyyaml==5.1',
    'voluptuous',
    'feedparser',
    'iso8601',
    'bcrypt==3.1.4',
    'paho-mqtt',
    'python-socketio',
    'deepdiff',
    'python-dateutil',
    'pid'
]

setup(
    name='appdaemon',
    version=__version__,
    description="Apps for the Home Assistant home automation package.",
    long_description="AppDaemon is a loosely coupled, multithreaded, sandboxed python execution environment with a plugin based architecture for writing automation apps for Home Assistant, MQTT and other home automation software. As of release 2.0.0 it also provides a configurable dashboard (HADashboard) suitable for wall mounted tablets.",
    author='Andrew I Cockburn',
    author_email='appdaemon@acockburn.com',
    url='https://github.com/home-assistant/appdaemon.git',
    packages=find_packages(exclude=['contrib', 'docs', 'tests*']),
    include_package_data=True,
    install_requires=REQUIRES,
    license='Apache License 2.0',
    zip_safe=False,
    keywords=['appdaemon', 'home', 'automation'],
    entry_points={
        'console_scripts': [
            'appdaemon = appdaemon.__main__:main'
        ]
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Home Automation',
    ],
)
