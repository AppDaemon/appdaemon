#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

with open('README.md') as readme_file:
    README = readme_file.read()

with open('HISTORY.md') as history_file:
    HISTORY = history_file.read()

#sudo apt-get install python3-aiohttp-dbg

REQUIREMENTS = [
    'daemonize',
    'configparser',
    'astral',
    'requests>=2.6.0',
    'sseclient',
    'websocket-client',
    'async',
    'aiohttp>=1.2.0',
    'Jinja2>=2.9.5',
    'aiohttp_jinja2',
    'pyyaml',
    'voluptuous',
]

setup(
    name='appdaemon',
    version='2.0.0beta3',
    description="Apps for the Home Assistant home automation package.",
    long_description=README + '\n\n' + HISTORY,
    author='Andrew I Cockburn',
    author_email='appdaemon@acockburn.com',
    url='https://github.com/home-assistant/appdaemon.git',
    packages=find_packages(exclude=['contrib', 'docs', 'tests*']),
    include_package_data=True,
    install_requires=REQUIREMENTS,
    license='Apache License 2.0',
    zip_safe=False,
    keywords=['appdaemon', 'home', 'automation'],
    entry_points={
        'console_scripts': [
            'appdaemon = appdaemon.appdaemon:main'
        ]
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Home Automation',
    ],
)
