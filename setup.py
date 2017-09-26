from setuptools import setup

setup(
    name='discord-curious',
    use_scm_version={
        "version_scheme": "guess-next-dev",
        "local_scheme": "dirty-tag"
    },
    packages=['curious', 'curious.core', 'curious.commands', 'curious.dataclasses',
              'curious.voice', 'curious.ext.loapi', 'curious.ext.paginator'],
    url='https://github.com/SunDwarf/curious',
    license='MIT',
    author='Laura Dickinson',
    author_email='l@veriny.tf',
    description='A curio library for the Discord API',
    setup_requires=[
        "setuptools_scm",
    ],
    install_requires=[
        "asyncwebsockets>=0.1",
        "curio>=0.7.0,<=0.8.0",
        "pylru==1.0.9",
        "oauthlib==2.0.2",
        "pytz",
        "asks>=1.2.2",
        "multidict>=2.1.6"
    ],
    extras_require={
        "voice": ["opuslib==1.1.0",
                  "PyNaCL==1.0.1"],
        "docs": ["guzzle_sphinx_theme", "sphinx", "sphinxcontrib-asyncio",
                 "sphinx-autodoc-typehints"]
    }
)
