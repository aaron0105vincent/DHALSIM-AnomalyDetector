import setuptools

setuptools.setup(
    name="dhalsim",
    version="1.1.1",
    url="https://github.com/Critical-Infrastructure-Systems-Lab/DHALSIM",
    project_urls={
        "Bug Tracker": "https://github.com/Critical-Infrastructure-Systems-Lab/DHALSIM/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        # "Operating System :: OS Independent",
    ],
    license='MIT',
    packages=['dhalsim'],
    install_requires=[
        'pyyaml==6.0.1',
        'pyyaml-include==2.1',
        'antlr4-python3-runtime==4.13.1',
        'progressbar2',
        'numpy==1.24.3',
        'wntr==1.3.2',
        'pandas==2.3.2',
        'matplotlib==3.10.5',
        'schema==0.7.7',
        'scapy==2.6.1',
        'pathlib==1.0.1',
        'testresources==2.0.2',
        'pytest-mock==3.14.1',
        'netaddr==1.3.0',
        'flaky==3.8.1',
        'pytest==8.4.1',
        'tensorflow==2.13.1',
        'scikit-learn==1.7.1',
        'keras==2.13.1',
        'mock==5.2.0'
    ],
    extras_require={
        'test': ['wget', 'coverage', 'pytest-cov'],
        'doc': ['sphinx', 'sphinx-rtd-theme', 'sphinx-prompt'],
    },
    python_requires=">=3.8.10",
    entry_points={
        'console_scripts': [
            'dhalsim = dhalsim.command_line:main',
        ],
    },
)
