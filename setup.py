# setup.py
from setuptools import setup

setup(
    name='django_i3tasks',
    version='0.0.2',
    description='Django app for manage async tasks by http requests',
    long_description='Django app for manage async tasks by http requests',
    url='https://github.com/sajlx/django-i3tasks',
    author='Ivan Bettarini',
    author_email='ivan.bettarini@gmail.com',
    license='GNU General Public License v3.0',
    packages=['django_i3tasks'],
    zip_safe=False,
    install_requires=[
        'django',
        'djangorestframework',
        'requests'
        # 'celery',
        # 'redis',
    ],
)