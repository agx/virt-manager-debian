# Copyright (C) 2013, 2014 Red Hat, Inc.
#
# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

import atexit
import imp
import os

# Need to do this before any tests or virtinst import
os.environ["VIRTINST_TEST_SUITE"] = "1"
# Need to do this before we import argcomplete
os.environ.pop("_ARC_DEBUG", None)

# pylint: disable=wrong-import-position
from virtinst import buildconfig
from virtinst import log
# This sets all the cli bits back to their defaults
imp.reload(buildconfig)

from tests import utils

virtinstall = None
virtclone = None
virtconvert = None
virtxml = None


def setup_logging():
    import logging
    rootLogger = logging.getLogger()
    for handler in rootLogger.handlers:
        rootLogger.removeHandler(handler)

    logging.basicConfig(level=logging.DEBUG,
                        format="%(levelname)-8s %(message)s")

    if utils.clistate.debug:
        rootLogger.setLevel(logging.DEBUG)
    else:
        rootLogger.setLevel(logging.ERROR)


def setup_cli_imports():
    _cleanup_imports = []

    def _cleanup_imports_cb():
        for f in _cleanup_imports:
            if os.path.exists(f):
                os.unlink(f)

    def _import(name, path):
        _cleanup_imports.append(path + "c")
        return imp.load_source(name, path)

    global virtinstall
    global virtclone
    global virtconvert
    global virtxml
    atexit.register(_cleanup_imports_cb)
    virtinstall = _import("virtinstall", "virt-install")
    virtclone = _import("virtclone", "virt-clone")
    virtconvert = _import("virtconvert", "virt-convert")
    virtxml = _import("virtxml", "virt-xml")
