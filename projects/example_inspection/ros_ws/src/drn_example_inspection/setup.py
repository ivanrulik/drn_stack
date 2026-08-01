from glob import glob
from setuptools import find_packages, setup


PACKAGE_NAME = "drn_example_inspection"


setup(
    name=PACKAGE_NAME,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{PACKAGE_NAME}"]),
        (f"share/{PACKAGE_NAME}", ["package.xml"]),
        (f"share/{PACKAGE_NAME}/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Ivan Rulik",
    maintainer_email="49820318+ivanrulik@users.noreply.github.com",
    description="Inert heartbeat example for the DRN project extension contract.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "heartbeat = drn_example_inspection.heartbeat_node:main",
        ],
    },
)
