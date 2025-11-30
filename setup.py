from setuptools import setup, find_packages

setup(
    name="homie-compute",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.0",
        "psutil>=5.9",
        "rich>=13.0",
        "docker>=7.0.0",
        "pyyaml>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "homie=homie.cli:cli",
        ],
    },
    python_requires=">=3.10",
)
