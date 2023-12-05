# !/usr/bin/env python
''' Setuptools configuration for tuxlayers '''

__copyright__ = "Copyright (c) 2023, Avnet EMG GmbH"
__license__ = "MIT"
__version__ = "0.1.0"
__status__ = "Development"

from setuptools import setup
from pip._internal.req import parse_requirements

required_packages = parse_requirements('requirements.txt', session=False)

setup(
    name='tuxlayers',
    version='0.1.0',
    python_requires='>=3.9',
    py_modules=['TuxLayers'],
    include_package_data=True,
    url='https://github.com/avs-sas/avs-sas-tuxlayers',
    description='''Patch management over repos and subrepos''',
    install_requires=[str(item.req) for item in required_packages],
    entry_points={
        'console_scripts': [
            'info = commands.info:info',
            'patchset = commands.patchset:patchset',
            'apply = commands.patchset:apply',
            'document = commands.patchset:document',
            'listsubmodules = commands.baseline:listsubmodules'
            'addbaseline = commands.baseline:addbaseline',
            'reverttobaseline = commands.baseline:reverttobaseline',
            'showbaselines = commands.baseline:showbaselines',
            'createpatches = commands.baseline:createpatches'
        ],
    },
)
