from setuptools import setup

setup(
    name='discord-curious',
    version='0.1.0',
    packages=['curious', 'curious.http', 'curious.commands', 'curious.dataclasses', 'curious.ext'],
    url='https://github.com/SunDwarf/curious',
    license='MIT',
    author='Laura Dickinson',
    author_email='l@veriny.tf',
    description='A curio library for the Discord API',
    install_requires=[
        "cuiows>=0.1.5",
        "curio==0.4.0",
        "h11==0.7.0",
        "multidict==2.1.4",
        "pylru==1.0.9",
        "yarl==0.8.1",
    ]
)
