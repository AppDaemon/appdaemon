#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

with open('README.md') as readme_file:
    README = readme_file.read()

with open('HISTORY.md') as history_file:
    HISTORY = history_file.read()

REQUIREMENTS = [
    'daemonize',
    'sseclient',
    'configparser',
    'astral',
    'requests>=2.6.0',
]

setup(
    name='appdaemon',
    version='1.1.1',
    description="Apps for the Home Assistant home automation package.",
    long_description=README + '\n\n' + HISTORY,
    author="Andrew I Cockburn",
    author_email='appdaemon@acockburn.com',
    url='https://github.com/acockburn/appdaemon',
    packages=find_packages(exclude=['contrib', 'docs', 'tests*']),
    include_package_data=True,
    install_requires=REQUIREMENTS,
    license="MIT license",
    zip_safe=False,
    keywords=['appdaemon', 'home', 'automation'],
    entry_points={
        'console_scripts': [
            'appdaemon = appdaemon.appdaemon:main'
        ]
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Home Automation',
    ],
)
