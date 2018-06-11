#!/usr/bin/env python

from setuptools import setup
from bobcat_rtpusher import __version__

setup(
    name='bobcat_rtpusher',
    version=__version__,
    description='Bobcat Realtime Pusher',
    author='Kirei AB',
    author_email='info@kirei.se',
    classifiers=['License :: Other/Proprietary License'],
    url='https://github.com/kirei/bobcat-rtpusher',
    packages=['bobcat_rtpusher'],
    install_requires=[
        'asyncio==3.4.3',
        'hbmqtt==0.9.2',
        'isodate==0.6.0',
        'pynmea2==1.12.0',
        'pyyaml==3.12',
        'setuptools',
        'websockets==4.0.1',
    ],
    package_data={'bobcat_rtpusher': [
        'schema/*.yaml',
    ]},
    data_files=[
        ('examples', ['examples/realtime_pusher.yaml']),
    ],
    entry_points={
        "console_scripts": [
            "realtime_pusher = bobcat_rtpusher.realtime_pusher:main"
        ]
    }
)
