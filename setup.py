from setuptools import setup

setup(name="zaz-telegram-py",
      version=0.1,
      description="Telegram plugin for Zenon AZ updates",
      url="https://github.com/dumeriz/zaz-telegram-py",
      author="Dumeril",
      author_email="zdumeril@gmail.com",
      license="MIT",
      packages=["zaz_telegram_py"],
      install_requires=[
          'pyzmq'
      ],
      entry_points = {
          'console_scripts': ['zaz-telegram-bot=zaz_telegram_py.main:main'],
      },
      zip_safe=False)
