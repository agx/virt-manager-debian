# Basic Install

For starters, if you just want to run `virt-manager/virt-install` to test out
changes, it can be done from the source directory:
```sh
./virt-manager
```

To install the software into `/usr/local` (usually), you can do:
```sh
./setup.py install
```

To build an RPM, you can run:
```sh
./setup.py rpm
```

`setup.py` generally has all the build and install commands, for more info see:

   - `./setup.py --help-commands`
   - `./setup.py install --help`
   - [Python Standard Build and Install](https://docs.python.org/3/install/#standard-build-and-install)


## Pre-requisite software

A detailed dependency list can be found in
[virt-manager.spec.in](virt-manager.spec.in) file.

Minimum version requirements of major components:

   - python >= 3.3
   - gtk3 >= 3.14
   - libvirt-python >= 0.6.0
   - pygobject3 >= 3.14
   - libosinfo >= 0.2.10

On Debian or Ubuntu based distributions, you need to install the
`gobject-introspection` bindings for some dependencies like `libvirt-glib`
and `libosinfo`. Look for package names that start with `'gir'`, for example
`gir1.2-libosinfo-1.0`.