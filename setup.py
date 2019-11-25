import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="blinkerc",
    version="0.0.1",
    author="weissger",
    author_email="thomas.weissgerber@uni-passau.de ",
    description="Class signals based on blinker",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Weissger/blinkerc",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)