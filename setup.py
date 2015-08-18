from setuptools import setup

setup(
    name='snesify',
    # NB: update snesify.py when changing this
    version='0.0',
    description="Converts graphics to SNES format",
    url='http://github.com/furrykef/snesify',
    author='Kef Schecter',
    author_email='furrykef@gmail.com',
    license='MIT',
    classifiers=[
        #'Development Status :: 5 - Production/Stable',
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.4',
        'Topic :: Multimedia :: Graphics',
        'Topic :: Utilities',
    ],
    py_modules=['snesify'],
    entry_points = {
        'console_scripts': ['snesify=snesify:main'],
    }
)
