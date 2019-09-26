#
# Copyright 2006-2009, 2013, 2014 Red Hat, Inc.
#
# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

import os
import shutil
import subprocess
import tempfile

from ..logger import log


def _run_initrd_commands(initrd, tempdir):
    log.debug("Appending to the initrd.")

    find_proc = subprocess.Popen(['find', '.', '-print0'],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 cwd=tempdir)
    cpio_proc = subprocess.Popen(['cpio', '--create', '--null', '--quiet',
                                  '--format=newc', '--owner=+0:+0'],
                                 stdin=find_proc.stdout,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 cwd=tempdir)
    f = open(initrd, 'ab')
    gzip_proc = subprocess.Popen(['gzip'], stdin=cpio_proc.stdout,
                                 stdout=f, stderr=subprocess.PIPE)
    cpio_proc.wait()
    find_proc.wait()
    gzip_proc.wait()
    f.close()

    finderr = find_proc.stderr.read()
    cpioerr = cpio_proc.stderr.read()
    gziperr = gzip_proc.stderr.read()
    if finderr:  # pragma: no cover
        log.debug("find stderr=%s", finderr)
    if cpioerr:  # pragma: no cover
        log.debug("cpio stderr=%s", cpioerr)
    if gziperr:  # pragma: no cover
        log.debug("gzip stderr=%s", gziperr)


def _run_iso_commands(iso, tempdir):
    cmd = ["genisoimage",
           "-o", iso,
           "-J",
           "-input-charset", "utf8",
           "-rational-rock",
           tempdir]
    log.debug("Running iso build command: %s", cmd)
    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    log.debug("cmd output: %s", output)


def _perform_generic_injections(injections, scratchdir, media, cb):
    if not injections:
        return

    tempdir = tempfile.mkdtemp(dir=scratchdir)
    try:
        os.chmod(tempdir, 0o775)

        for filename in injections:
            if type(filename) is tuple:
                filename, dst = filename
            else:
                dst = os.path.basename(filename)

            log.debug("Injecting src=%s dst=%s into media=%s",
                    filename, dst, media)
            shutil.copy(filename, os.path.join(tempdir, dst))

        return cb(media, tempdir)
    finally:
        shutil.rmtree(tempdir)


def perform_initrd_injections(initrd, injections, scratchdir):
    """
    Insert files into the root directory of the initial ram disk
    """
    _perform_generic_injections(injections, scratchdir, initrd,
            _run_initrd_commands)


def perform_cdrom_injections(injections, scratchdir):
    """
    Insert files into the root directory of a generated cdrom
    """
    fileobj = tempfile.NamedTemporaryFile(
        prefix="virtinst-", suffix="-unattended.iso",
        dir=scratchdir, delete=False)
    iso = fileobj.name

    try:
        _perform_generic_injections(injections, scratchdir, iso,
            _run_iso_commands)
    except Exception:  # pragma: no cover
        os.unlink(iso)
        raise

    return iso
