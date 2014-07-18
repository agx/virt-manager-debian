#
# Common code for all guests
#
# Copyright 2006-2009, 2013 Red Hat, Inc.
# Jeremy Katz <katzj@redhat.com>
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

import os
import logging

import virtinst
from virtinst import OSXML


class Installer(object):
    """
    Installer classes attempt to encapsulate all the parameters needed
    to 'install' a guest: essentially, booting the guest with the correct
    media for the OS install phase (if there is one), and setting up the
    guest to boot to the correct media for all subsequent runs.

    Some of the actual functionality:

        - Determining what type of install media has been requested, and
          representing it correctly to the Guest

        - Fetching install kernel/initrd or boot.iso from a URL

        - Setting the boot device as appropriate depending on whether we
          are booting into an OS install, or booting post-install

    Some of the information that the Installer needs to know to accomplish
    this:

        - Install media location (could be a URL, local path, ...)
        - Virtualization type (parameter 'os_type') ('xen', 'hvm', etc.)
        - Hypervisor name (parameter 'type') ('qemu', 'kvm', 'xen', etc.)
        - Guest architecture ('i686', 'x86_64')
    """
    _has_install_phase = True

    def __init__(self, conn):
        self.conn = conn
        self._location = None

        self.cdrom = False
        self.extraargs = None

        self.initrd_injections = []

        self._install_kernel = None
        self._install_initrd = None

        # Devices created/added during the prepare() stage
        self.install_devices = []

        self._tmpfiles = []
        self._tmpvols = []


    #########################
    # Properties properties #
    #########################

    def get_location(self):
        return self._location
    def set_location(self, val):
        self._location = self._validate_location(val)
    location = property(get_location, set_location)


    ###################
    # Private helpers #
    ###################

    def _build_boot_order(self, isinstall, guest):
        bootorder = [self._get_bootdev(isinstall, guest)]

        # If guest has an attached disk, always have 'hd' in the boot
        # list, so disks are marked as bootable/installable (needed for
        # windows virtio installs, and booting local disk from PXE)
        for disk in guest.get_devices("disk"):
            if disk.device == disk.DEVICE_DISK:
                bootdev = "hd"
                if bootdev not in bootorder:
                    bootorder.append(bootdev)
                break
        return bootorder

    def _make_cdrom_dev(self, path, transient=False):
        dev = virtinst.VirtualDisk(self.conn)
        dev.path = path
        dev.device = dev.DEVICE_CDROM
        dev.read_only = True
        dev.transient = transient

        dev.validate()
        return dev

    def alter_bootconfig(self, guest, isinstall, bootconfig):
        """
        Generate the portion of the guest xml that determines boot devices
        and parameters. (typically the <os></os> block)

        @param guest: Guest instance we are installing
        @type guest: L{Guest}
        @param isinstall: Whether we want xml for the 'install' phase or the
                          'post-install' phase.
        @type isinstall: C{bool}
        """
        if isinstall and not self.has_install_phase():
            return

        bootorder = self._build_boot_order(isinstall, guest)

        if not bootconfig.bootorder:
            # Per device <boot order> is not compatible with os/boot.
            if not any(d.boot.order for d in guest.get_all_devices()):
                bootconfig.bootorder = bootorder

        if not isinstall:
            return

        if self._install_kernel:
            bootconfig.kernel = self._install_kernel
        if self._install_initrd:
            bootconfig.initrd = self._install_initrd
        if self.extraargs:
            bootconfig.kernel_args = self.extraargs


    ##########################
    # Internal API overrides #
    ##########################

    def _get_bootdev(self, isinstall, guest):
        raise NotImplementedError("Must be implemented in subclass")

    def _validate_location(self, val):
        return val

    def _prepare(self, guest, meter, scratchdir):
        ignore = guest
        ignore = meter
        ignore = scratchdir


    ##############
    # Public API #
    ##############

    def scratchdir_required(self):
        """
        Returns true if scratchdir is needed for the passed install parameters.
        Apps can use this to determine if they should attempt to ensure
        scratchdir permissions are adequate
        """
        return False

    def has_install_phase(self):
        """
        Return True if the requested setup is actually installing an OS
        into the guest. Things like LiveCDs, Import, or a manually specified
        bootorder do not have an install phase.
        """
        return self._has_install_phase

    def cleanup(self):
        """
        Remove any temporary files retrieved during installation
        """
        for f in self._tmpfiles:
            logging.debug("Removing " + f)
            os.unlink(f)

        for vol in self._tmpvols:
            logging.debug("Removing volume '%s'", vol.name())
            vol.delete(0)

        self._tmpvols = []
        self._tmpfiles = []
        self.install_devices = []

    def prepare(self, guest, meter, scratchdir):
        self.cleanup()
        try:
            self._prepare(guest, meter, scratchdir)
        except:
            self.cleanup()
            raise

    def check_location(self, guest):
        """
        Validate self.location seems to work. This will might hit the
        network so we don't want to do it on demand.
        """
        ignore = guest
        return True

    def detect_distro(self, guest):
        """
        Attempt to detect the distro for the Installer's 'location'. If
        an error is encountered in the detection process (or if detection
        is not relevant for the Installer type), (None, None) is returned

        @returns: (distro type, distro variant) tuple
        """
        ignore = guest
        return (None, None)


class ContainerInstaller(Installer):
    _has_install_phase = False
    def _get_bootdev(self, isinstall, guest):
        ignore = isinstall
        ignore = guest
        return OSXML.BOOT_DEVICE_HARDDISK


class PXEInstaller(Installer):
    def _get_bootdev(self, isinstall, guest):
        bootdev = OSXML.BOOT_DEVICE_NETWORK

        if (not isinstall and
            [d for d in guest.get_devices("disk") if
             d.device == d.DEVICE_DISK]):
            # If doing post-install boot and guest has an HD attached
            bootdev = OSXML.BOOT_DEVICE_HARDDISK

        return bootdev


class LiveCDInstaller(Installer):
    _has_install_phase = False
    cdrom = True

    def _validate_location(self, val):
        return self._make_cdrom_dev(val).path
    def _prepare(self, guest, meter, scratchdir):
        ignore = guest
        ignore = meter
        ignore = scratchdir
        self.install_devices.append(self._make_cdrom_dev(self.location))
    def _get_bootdev(self, isinstall, guest):
        return OSXML.BOOT_DEVICE_CDROM


class ImportInstaller(Installer):
    _has_install_phase = False

    # Private methods
    def _get_bootdev(self, isinstall, guest):
        disks = guest.get_devices("disk")
        if not disks:
            return OSXML.BOOT_DEVICE_HARDDISK
        return self._disk_to_bootdev(disks[0])

    def _disk_to_bootdev(self, disk):
        if disk.device == virtinst.VirtualDisk.DEVICE_DISK:
            return OSXML.BOOT_DEVICE_HARDDISK
        elif disk.device == virtinst.VirtualDisk.DEVICE_CDROM:
            return OSXML.BOOT_DEVICE_CDROM
        elif disk.device == virtinst.VirtualDisk.DEVICE_FLOPPY:
            return OSXML.BOOT_DEVICE_FLOPPY
        else:
            return OSXML.BOOT_DEVICE_HARDDISK
