from setuptools import setup

setup(
    name='curious',
    version='0.1.0',
    packages=['curious', 'curious.http', 'curious.commands', 'curious.dataclasses'],
    url='https://github.com/SunDwarf/curious',
    license='MIT',
    author='Laura Dickinson',
    author_email='l@veriny.tf',
    description='A curio library for the Discord API',
    install_requires=[
        "cuiows>=0.1.5",
        "curio==0.4.0"
    ]
)
