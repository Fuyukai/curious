from setuptools import setup

setup(
    name='discord-curious',
    version='0.3.0',
    packages=['curious', 'curious.core', 'curious.http', 'curious.commands', 'curious.dataclasses', 'curious.voice',
              'curious.ext.loapi', 'curious.ext.paginator'],
    url='https://github.com/SunDwarf/curious',
    license='MIT',
    author='Laura Dickinson',
    author_email='l@veriny.tf',
    description='A curio library for the Discord API',
    install_requires=[
        "cuiows>=0.1.10",
        "curio==0.6.0",
        "h11==0.7.0",
        "multidict==2.1.4",
        "pylru==1.0.9",
        "yarl==0.8.1",
    ],
    extras_require={
        "voice": ["opuslib==1.1.0",
                "PyNaCL==1.0.1"],
        "docs": ["guzzle_sphinx_theme", "sphinx", "sphinxcontrib-asyncio"]
    }
)
