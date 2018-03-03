import sys
from pathlib import Path

from setuptools import setup

install_requires = [
        "lomond>=0.1.13,<0.2",
        "pylru==1.0.9",
        "oauthlib>=2.0.2,<2.1.0",
        "pytz>=2017.3",
        "asks>=1.3.0,<1.4.0",
        "multidict>=4.1.0,<4.2.0",
        "multio>=0.2.1,<0.3.0",
        "async_generator~=1.9",  # asynccontextmanager for 3.6
        "typing_inspect>=0.2.0"
]

py36_requires = [
    "dataclasses>=0.3",  # PEP 557
    # pending 567 backport
]

if sys.version_info[0:2] <= (3, 6):
    install_requires += py36_requires


setup(
    name='discord-curious',
    use_scm_version={
        "version_scheme": "guess-next-dev",
        "local_scheme": "dirty-tag"
    },
    packages=['curious', 'curious.core', 'curious.core._ws_wrapper',
              'curious.commands', 'curious.dataclasses',
              'curious.ext.paginator', 'curious.ipc'],
    url='https://github.com/SunDwarf/curious',
    license='LGPLv3',
    author='Laura Dickinson',
    author_email='l@veriny.tf',
    description='An async library for the Discord API',
    long_description=Path(__file__).with_name("README.rst").read_text(encoding="utf-8"),
    python_requires=">=3.6.2",
    setup_requires=[
        "setuptools_scm",
    ],
    classifiers=[
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3 :: Only",
        "Framework :: Trio",
        "Development Status :: 4 - Beta"
    ],
    install_requires=install_requires,
    extras_require={
        "voice": ["opuslib==1.1.0",
                  "PyNaCL==1.0.1"],
        "docs": [
            "sphinx_py3doc_enhanced_theme",
            "sphinx",
            "sphinxcontrib-asyncio",
            "sphinx-autodoc-typehints",
        ]
    },
)
