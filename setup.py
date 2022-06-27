#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

from appdaemon.version import __version__

# sudo apt-get install python3-aiohttp-dbg

with open("requirements.txt") as f:
    install_requires = [x for x in f.read().split("\n") if x]

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
    install_requires=install_requires,
    license="Apache License 2.0",
    python_requires=">=3.7",
    zip_safe=False,
    keywords=["appdaemon", "home", "automation"],
    entry_points={"console_scripts": ["appdaemon = appdaemon.__main__:main"]},
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Home Automation",
    ],
)
