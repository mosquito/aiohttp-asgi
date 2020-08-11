import os
from setuptools import setup, find_packages
from importlib.machinery import SourceFileLoader


module = SourceFileLoader(
    "version", os.path.join("aiohttp_asgi", "version.py")
).load_module()


setup(
    name="aiohttp-asgi",
    version=module.__version__,
    author=module.__author__,
    author_email=module.team_email,
    license=module.package_license,
    description=module.package_info,
    long_description_content_type='text/markdown',
    long_description=open("README.md").read(),
    platforms="all",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: Apache Software License",
        "Topic :: Internet",
        "Topic :: Software Development",
        "Topic :: Software Development :: Libraries",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Operating System :: MacOS",
        "Operating System :: POSIX",
        "Operating System :: Microsoft",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: Implementation :: PyPy",
        "Programming Language :: Python :: Implementation :: CPython",
    ],
    packages=find_packages(exclude=["tests"]),
    package_data={"aiohttp_asgi": ["py.typed"]},
    install_requires=["aiohttp"],
    python_requires=">3.5.*, <4",
    extras_require={
        "develop": [
            "aiomisc~=10.1.6",
            "async_generator",
            "coverage!=4.3",
            "coveralls",
            "pylava",
            "pytest",
            "pytest-cov",
            "tox>=2.4",
        ],
    },
    entry_points={
        'console_scripts': ['aiohttp-asgi = aiohttp_asgi.__main__:main']
    },
    project_urls={
        "Source": "https://github.com/mosquito/aiohttp-asgi",
    },
)
