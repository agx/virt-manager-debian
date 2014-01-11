#
# Copyright (C) 2011 Red Hat, Inc.
# Copyright (C) 2011 Cole Robinson <crobinso@redhat.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301 USA.
#

import gettext
import locale
import logging
import logging.handlers
import os
import sys
import traceback

import libvirt

from virtcli import cliconfig



def setup_logging(appname, debug_stdout):
    # Configure python logging to capture all logs we generate
    # to $HOME/.virt-manager/${app}.log This file has
    # proved invaluable for debugging
    MAX_LOGSIZE   = 1024 * 1024  # 1MB
    ROTATE_NUM    = 5
    DIR_NAME      = ".virt-manager"
    FILE_NAME     = "%s.log" % appname
    FILE_MODE     = 'ae'
    FILE_FORMAT   = ("[%(asctime)s virt-manager %(process)d] "
                     "%(levelname)s (%(module)s:%(lineno)d) %(message)s")
    DATEFMT       = "%a, %d %b %Y %H:%M:%S"

    # set up logging
    vm_dir = os.path.expanduser("~/%s" % DIR_NAME)
    if not os.access(vm_dir, os.W_OK):
        if os.path.exists(vm_dir):
            raise RuntimeError("No write access to %s" % vm_dir)

        try:
            os.mkdir(vm_dir, 0751)
        except IOError, e:
            raise RuntimeError("Could not create directory %s: %s" %
                               (vm_dir, e))

    filename = "%s/%s" % (vm_dir, FILE_NAME)
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)
    fileHandler = logging.handlers.RotatingFileHandler(filename,
                                    FILE_MODE, MAX_LOGSIZE, ROTATE_NUM)
    fileHandler.setFormatter(logging.Formatter(FILE_FORMAT, DATEFMT))
    rootLogger.addHandler(fileHandler)

    if debug_stdout:
        streamHandler = logging.StreamHandler(sys.stderr)
        streamHandler.setLevel(logging.DEBUG)
        streamHandler.setFormatter(logging.Formatter(
                        "%(asctime)s (%(module)s:%(lineno)d): %(message)s"))
        rootLogger.addHandler(streamHandler)

    logging.info("%s startup", appname)

    # Register libvirt handler
    def libvirt_callback(ctx_ignore, err):
        if err[3] != libvirt.VIR_ERR_ERROR:
            # Don't log libvirt errors: global error handler will do that
            logging.warn("Non-error from libvirt: '%s'", err[2])
    libvirt.registerErrorHandler(f=libvirt_callback, ctx=None)

    # Log uncaught exceptions
    def exception_log(typ, val, tb):
        s = traceback.format_exception(typ, val, tb)
        logging.debug("Uncaught exception:\n" + "".join(s))
        sys.__excepthook__(typ, val, tb)
    sys.excepthook = exception_log


def setup_i18n():
    try:
        locale.setlocale(locale.LC_ALL, '')
    except:
        # Can happen if user passed a bogus LANG
        pass

    gettext.install("virt-manager", cliconfig.gettext_dir)
    gettext.bindtextdomain("virt-manager", cliconfig.gettext_dir)
