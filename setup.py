"""翻唱歌曲项目管理工具"""

from setuptools import setup, find_packages

setup(
    name="cover-manager",
    version="0.1.0",
    description="翻唱歌曲项目管理命令行工具",
    author="Cover Manager",
    packages=find_packages(),
    install_requires=[
        "click>=8.0.0",
    ],
    entry_points={
        "console_scripts": [
            "cover-mgr=cover_manager.cli:main",
        ],
    },
    python_requires=">=3.8",
)
