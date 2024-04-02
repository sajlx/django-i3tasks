# setup.py
from setuptools import setup

from pathlib import Path
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name='django_i3tasks',
    version='0.0.8',
    description='Django app for manage async tasks by http requests',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/sajlx/django-i3tasks',
    author='Ivan Bettarini',
    author_email='ivan.bettarini@gmail.com',
    license='GNU General Public License v3.0',
    packages=['django_i3tasks'],
    zip_safe=False,
    install_requires=[
        'django',
        'djangorestframework',
        'requests',
        'croniter>=2.0.1'
        # 'celery',
        # 'redis',
    ],
    classifiers=[
        'Environment :: Web Environment',
        'Operating System :: OS Independent',
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Framework :: Django'
    ]
)