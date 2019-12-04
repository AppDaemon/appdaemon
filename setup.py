#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

from appdaemon.version import __version__

# sudo apt-get install python3-aiohttp-dbg

REQUIRES = [
    "daemonize",
    "astral",
    "pytz",
    "requests>=2.6.0",
    "sseclient",
    "websocket-client",
    "aiohttp==3.4.4",
    "yarl==1.1.0",
    "Jinja2==2.10.1",
    "aiohttp_jinja2==0.15.0",
    "pyyaml==5.1",
    "voluptuous",
    "feedparser",
    "iso8601",
    "bcrypt==3.1.4",
    "paho-mqtt",
    "python-socketio",
    "deepdiff",
    "python-dateutil",
    "pid",
]

with open("README.md") as f:
    long_description = f.read()

setup(
    name="appdaemon",
    version=__version__,
    description="Apps for the Home Assistant home automation package.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Andrew I Cockburn",
    author_email="appdaemon@acockburn.com",
    url="https://github.com/home-assistant/appdaemon.git",
    packages=find_packages(exclude=["contrib", "docs", "tests*"]),
    include_package_data=True,
    install_requires=REQUIRES,
    license="Apache License 2.0",
    python_requires=">=3.6",
    zip_safe=False,
    keywords=["appdaemon", "home", "automation"],
    entry_points={"console_scripts": ["appdaemon = appdaemon.__main__:main"]},
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Home Automation",
    ],
)
