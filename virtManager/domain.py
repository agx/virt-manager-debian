#
# Copyright (C) 2006, 2013, 2014 Red Hat, Inc.
# Copyright (C) 2006 Daniel P. Berrange <berrange@redhat.com>
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

# pylint: disable=E0611
from gi.repository import GObject
# pylint: enable=E0611

import logging
import os
import time
import threading

import libvirt

from virtinst import DomainSnapshot
from virtinst import Guest
from virtinst import util
from virtinst import VirtualController

from virtManager.libvirtobject import vmmLibvirtObject

if not hasattr(libvirt, "VIR_DOMAIN_PMSUSPENDED"):
    setattr(libvirt, "VIR_DOMAIN_PMSUSPENDED", 7)

vm_status_icons = {
    libvirt.VIR_DOMAIN_BLOCKED: "state_running",
    libvirt.VIR_DOMAIN_CRASHED: "state_shutoff",
    libvirt.VIR_DOMAIN_PAUSED: "state_paused",
    libvirt.VIR_DOMAIN_RUNNING: "state_running",
    libvirt.VIR_DOMAIN_SHUTDOWN: "state_shutoff",
    libvirt.VIR_DOMAIN_SHUTOFF: "state_shutoff",
    libvirt.VIR_DOMAIN_NOSTATE: "state_running",
    libvirt.VIR_DOMAIN_PMSUSPENDED: "state_paused",
}


class _SENTINEL(object):
    pass


def compare_device(origdev, newdev, idx):
    devprops = {
        "disk"      : ["target", "bus"],
        "interface" : ["macaddr", "vmmindex"],
        "input"     : ["bus", "type", "vmmindex"],
        "sound"     : ["model", "vmmindex"],
        "video"     : ["model", "vmmindex"],
        "watchdog"  : ["vmmindex"],
        "hostdev"   : ["type", "managed", "vmmindex",
                       "product", "vendor",
                       "function", "domain", "slot"],
        "serial"    : ["type", "target_port"],
        "parallel"  : ["type", "target_port"],
        "console"   : ["type", "target_type", "target_port"],
        "graphics"  : ["type", "vmmindex"],
        "controller" : ["type", "index"],
        "channel"   : ["type", "target_name"],
        "filesystem" : ["target" , "vmmindex"],
        "smartcard" : ["mode" , "vmmindex"],
        "redirdev" : ["bus" , "type", "vmmindex"],
        "tpm"       : ["type" , "vmmindex"],
        "rng"       : ["type" , "vmmindex"],
        "panic"       : ["type" , "vmmindex"],
    }

    if id(origdev) == id(newdev):
        return True

    if type(origdev) is not type(newdev):
        return False

    for devprop in devprops[origdev.virtual_device_type]:
        origval = getattr(origdev, devprop)
        if devprop == "vmmindex":
            newval = idx
        else:
            newval = getattr(newdev, devprop)

        if origval != newval:
            return False

    return True


def _find_device(guest, origdev):
    devlist = guest.get_devices(origdev.virtual_device_type)
    for idx in range(len(devlist)):
        dev = devlist[idx]
        if compare_device(origdev, dev, idx):
            return dev

    return None


def start_job_progress_thread(vm, meter, progtext):
    current_thread = threading.currentThread()

    def jobinfo_cb():
        while True:
            time.sleep(.5)

            if not current_thread.isAlive():
                return False

            try:
                jobinfo = vm.job_info()
                data_total      = float(jobinfo[3])
                # data_processed  = float(jobinfo[4])
                data_remaining  = float(jobinfo[5])

                # data_total is 0 if the job hasn't started yet
                if not data_total:
                    continue

                if not meter.started:
                    meter.start(size=data_total,
                                text=progtext)

                progress = data_total - data_remaining
                meter.update(progress)
            except:
                logging.exception("Error calling jobinfo")
                return False

        return True

    if vm.getjobinfo_supported:
        t = threading.Thread(target=jobinfo_cb,
                             name="job progress reporting",
                             args=())
        t.daemon = True
        t.start()


class vmmInspectionData(object):
    def __init__(self):
        self.type = None
        self.distro = None
        self.major_version = None
        self.minor_version = None
        self.hostname = None
        self.product_name = None
        self.product_variant = None
        self.icon = None
        self.applications = None
        self.error = False


class vmmDomainSnapshot(vmmLibvirtObject):
    """
    Class wrapping a virDomainSnapshot object
    """
    def __init__(self, conn, backend):
        vmmLibvirtObject.__init__(self, conn, backend, backend.getName(),
                                  DomainSnapshot)

        self.refresh_xml()

    def get_name(self):
        return self.get_xmlobj().name
    def _XMLDesc(self, flags):
        return self._backend.getXMLDesc(flags=flags)

    def delete(self, force=True):
        ignore = force
        self._backend.delete()

    def run_status(self):
        status = DomainSnapshot.state_str_to_int(self.get_xmlobj().state)
        return vmmDomain.pretty_run_status(status)
    def run_status_icon_name(self):
        status = DomainSnapshot.state_str_to_int(self.get_xmlobj().state)
        if status not in vm_status_icons:
            logging.debug("Unknown status %d, using NOSTATE", status)
            status = libvirt.VIR_DOMAIN_NOSTATE
        return vm_status_icons[status]

    def is_current(self):
        return self._backend.isCurrent()
    def is_external(self):
        if self.get_xmlobj().memory_type == "external":
            return True
        for disk in self.get_xmlobj().disks:
            if disk.snapshot == "external":
                return True
        return False


class vmmDomain(vmmLibvirtObject):
    """
    Class wrapping virDomain libvirt objects. Is also extended to be
    backed by a virtinst.Guest object for new VM 'customize before install'
    """
    __gsignals__ = {
        "status-changed": (GObject.SignalFlags.RUN_FIRST, None, [int, int]),
        "resources-sampled": (GObject.SignalFlags.RUN_FIRST, None, []),
        "inspection-changed": (GObject.SignalFlags.RUN_FIRST, None, []),
        "pre-startup": (GObject.SignalFlags.RUN_FIRST, None, [object]),
    }

    @staticmethod
    def pretty_run_status(status, has_saved=False):
        if status == libvirt.VIR_DOMAIN_RUNNING:
            return _("Running")
        elif status == libvirt.VIR_DOMAIN_PAUSED:
            return _("Paused")
        elif status == libvirt.VIR_DOMAIN_SHUTDOWN:
            return _("Shutting Down")
        elif status == libvirt.VIR_DOMAIN_SHUTOFF:
            if has_saved:
                return _("Saved")
            else:
                return _("Shutoff")
        elif status == libvirt.VIR_DOMAIN_CRASHED:
            return _("Crashed")
        elif status == libvirt.VIR_DOMAIN_PMSUSPENDED:
            return _("Suspended")

        logging.debug("Unknown status %d, returning 'Unknown'", status)
        return _("Unknown")

    @staticmethod
    def pretty_status_reason(status, reason):
        key = lambda x, y: getattr(libvirt, "VIR_DOMAIN_" + x, y)
        reasons = {
            libvirt.VIR_DOMAIN_RUNNING : {
                key("RUNNING_BOOTED", 1) : _("Booted"),
                key("RUNNING_MIGRATED", 2) : _("Migrated"),
                key("RUNNING_RESTORED", 3) : _("Restored"),
                key("RUNNING_FROM_SNAPSHOT", 4) : _("From snapshot"),
                key("RUNNING_UNPAUSED", 5) : _("Unpaused"),
                key("RUNNING_MIGRATION_CANCELED", 6) : _("Migration canceled"),
                key("RUNNING_SAVE_CANCELED", 7) : _("Save canceled"),
                key("RUNNING_WAKEUP", 8) : _("Event wakeup"),
                key("RUNNING_CRASHED", 9) : _("Crashed"),
            },
            libvirt.VIR_DOMAIN_PAUSED : {
                key("PAUSED_USER", 1) : _("User"),
                key("PAUSED_MIGRATION", 2) : _("Migrating"),
                key("PAUSED_SAVE", 3) : _("Saving"),
                key("PAUSED_DUMP", 4) : _("Dumping"),
                key("PAUSED_IOERROR", 5) : _("I/O error"),
                key("PAUSED_WATCHDOG", 6) : _("Watchdog"),
                key("PAUSED_FROM_SNAPSHOT", 7) : _("From snapshot"),
                key("PAUSED_SHUTTING_DOWN", 8) : _("Shutting down"),
                key("PAUSED_SNAPSHOT", 9) : _("Creating snapshot"),
                key("PAUSED_CRASHED", 10) : _("Crashed"),
            },
            libvirt.VIR_DOMAIN_SHUTDOWN : {
                key("SHUTDOWN_USER", 1) : _("User"),
            },
            libvirt.VIR_DOMAIN_SHUTOFF : {
                key("SHUTOFF_SHUTDOWN", 1) : _("Shutdown"),
                key("SHUTOFF_DESTROYED", 2) : _("Destroyed"),
                key("SHUTOFF_CRASHED", 3) : _("Crashed"),
                key("SHUTOFF_MIGRATED", 4) : _("Migrated"),
                key("SHUTOFF_SAVED", 5) : _("Saved"),
                key("SHUTOFF_FAILED", 6) : _("Failed"),
                key("SHUTOFF_FROM_SNAPSHOT", 7) : _("From snapshot"),
            },
            libvirt.VIR_DOMAIN_CRASHED : {
                key("CRASHED_PANICKED", 1) : _("Panicked"),
            }
        }
        return reasons.get(status) and reasons[status].get(reason)

    def __init__(self, conn, backend, key):
        vmmLibvirtObject.__init__(self, conn, backend, key, Guest)

        self.uuid = key
        self.cloning = False

        self.record = []
        self.maxRecord = {
            "diskRdRate" : 10.0,
            "diskWrRate" : 10.0,
            "netTxRate"  : 10.0,
            "netRxRate"  : 10.0,
        }

        self._install_abort = False
        self.reboot_listener = None
        self._is_management_domain = None
        self._id = None
        self._name = None
        self._snapshot_list = None

        self.lastStatus = libvirt.VIR_DOMAIN_SHUTOFF
        self._lastStatusReason = getattr(libvirt, "VIR_DOMAIN_SHUTOFF_SHUTDOWN",
                                         1)

        self.managedsave_supported = False
        self.remote_console_supported = False
        self.title_supported = False
        self.mem_stats_supported = False
        self.domain_state_supported = False

        self._enable_mem_stats = False
        self._enable_cpu_stats = False

        self._enable_net_poll = False
        self._stats_net_supported = True
        self._stats_net_skip = []

        self._enable_disk_poll = False
        self._stats_disk_supported = True
        self._stats_disk_skip = []
        self._summary_disk_stats_skip = False

        self.inspection = vmmInspectionData()

        if isinstance(self._backend, Guest):
            return

        self._libvirt_init()

    def _cleanup(self):
        for snap in self._snapshot_list or []:
            snap.cleanup()
        self._snapshot_list = None

    def _libvirt_init(self):
        """
        Initialization to do if backed by a libvirt virDomain
        """
        self.managedsave_supported = self.conn.check_support(
            self.conn.SUPPORT_DOMAIN_MANAGED_SAVE, self._backend)
        self.remote_console_supported = self.conn.check_support(
            self.conn.SUPPORT_DOMAIN_CONSOLE_STREAM, self._backend)
        self.title_supported = self.conn.check_support(
            self.conn.SUPPORT_DOMAIN_GET_METADATA, self._backend)
        self.mem_stats_supported = self.conn.check_support(
            self.conn.SUPPORT_DOMAIN_MEMORY_STATS, self._backend)
        self.domain_state_supported = self.conn.check_support(
            self.conn.SUPPORT_DOMAIN_STATE, self._backend)

        # Determine available XML flags (older libvirt versions will error
        # out if passed SECURE_XML, INACTIVE_XML, etc)
        (self._inactive_xml_flags,
         self._active_xml_flags) = self.conn.get_dom_flags(self._backend)

        self.toggle_sample_network_traffic()
        self.toggle_sample_disk_io()
        self.toggle_sample_mem_stats()
        self.toggle_sample_cpu_stats()

        self.force_update_status(from_event=True)

        # Hook up listeners that need to be cleaned up
        self.add_gconf_handle(
            self.config.on_stats_enable_cpu_poll_changed(
                self.toggle_sample_cpu_stats))
        self.add_gconf_handle(
            self.config.on_stats_enable_net_poll_changed(
                self.toggle_sample_network_traffic))
        self.add_gconf_handle(
            self.config.on_stats_enable_disk_poll_changed(
                self.toggle_sample_disk_io))
        self.add_gconf_handle(
            self.config.on_stats_enable_memory_poll_changed(
                self.toggle_sample_mem_stats))

        self.connect("pre-startup", self._prestartup_nodedev_check)

    def _prestartup_nodedev_check(self, src, ret):
        ignore = src
        error = _("There is more than one '%s' device attached to "
                  "your host, and we can't determine which one to "
                  "use for your guest.\n"
                  "To fix this, remove and reattach the USB device "
                  "to your guest using the 'Add Hardware' wizard.")

        for hostdev in self.get_hostdev_devices():
            devtype = hostdev.type

            if devtype != "usb":
                continue

            vendor = hostdev.vendor
            product = hostdev.product
            bus = hostdev.bus
            device = hostdev.device

            if vendor and product:
                count = self.conn.get_nodedevs_number("usb_device",
                                                      vendor,
                                                      product)
                if count > 1 and not (bus and device):
                    prettyname = "%s %s" % (vendor, product)
                    ret.append(error % prettyname)


    ###########################
    # Misc API getter methods #
    ###########################

    def _using_events(self):
        return self.conn.using_domain_events

    def get_name(self):
        if self._name is None:
            self._name = self._backend.name()
        return self._name

    def get_id(self):
        if self._id is None:
            self._id = self._backend.ID()
        return self._id

    def status(self):
        return self.lastStatus

    def status_reason(self):
        return self._lastStatusReason

    def get_cloning(self):
        return self.cloning
    def set_cloning(self, val):
        self.cloning = bool(val)

    # If manual shutdown or destroy specified, make sure we don't continue
    # install process
    def get_install_abort(self):
        return bool(self._install_abort)

    def stable_defaults(self):
        return self.conn.stable_defaults(self.get_emulator())

    def is_read_only(self):
        if self.is_management_domain():
            return True
        return False

    def is_management_domain(self):
        if self._is_management_domain is None:
            self._is_management_domain = (self.conn.is_xen() and
                                          self.get_id() == 0)
        return self._is_management_domain

    def has_spicevmc_type_redirdev(self):
        devs = self.get_redirdev_devices()
        for dev in devs:
            if dev.type == "spicevmc":
                return True
        return False

    def get_id_pretty(self):
        i = self.get_id()
        if i < 0:
            return "-"
        return str(i)

    ##################
    # Support checks #
    ##################

    def _get_getvcpus_supported(self):
        return self.conn.check_support(
            self.conn.SUPPORT_DOMAIN_GETVCPUS, self._backend)
    getvcpus_supported = property(_get_getvcpus_supported)

    def _get_getjobinfo_supported(self):
        return self.conn.check_support(
            self.conn.SUPPORT_DOMAIN_JOB_INFO, self._backend)
    getjobinfo_supported = property(_get_getjobinfo_supported)

    def snapshots_supported(self):
        if not self.conn.check_support(
            self.conn.SUPPORT_DOMAIN_LIST_SNAPSHOTS, self._backend):
            return _("Libvirt connection does not support snapshots.")

        if self.list_snapshots():
            return

        # Check if our disks are all qcow2
        seen_qcow2 = False
        for disk in self.get_disk_devices(refresh_if_nec=False):
            if disk.read_only:
                continue
            if not disk.path:
                continue
            if disk.driver_type == "qcow2":
                seen_qcow2 = True
                continue
            return _("Snapshots are only supported if all writeable disks "
                     "images allocated to the guest are qcow2 format.")
        if not seen_qcow2:
            return _("Snapshots require at least one writeable qcow2 disk "
                     "image allocated to the guest.")


    #############################
    # Internal XML handling API #
    #############################

    def _invalidate_xml(self):
        vmmLibvirtObject._invalidate_xml(self)
        self._name = None
        self._id = None

    def _lookup_device_to_define(self, origdev, guest=None):
        if guest is None:
            guest = self._get_xmlobj_to_define()

        dev = _find_device(guest, origdev)
        if dev:
            return dev

        # If we are removing multiple dev from an active VM, a double
        # attempt may result in a lookup failure. If device is present
        # in the active XML, assume all is good.
        if _find_device(self.get_xmlobj(), origdev):
            logging.debug("Device in active config but not inactive config.")
            return

        raise RuntimeError(_("Could not find specified device in the "
                             "inactive VM configuration: %s") % repr(origdev))

    def _redefine_device(self, cb, origdev, use_live_device):
        if not use_live_device:
            dev = self._lookup_device_to_define(origdev)
        else:
            dev = origdev
        if dev:
            cb(dev)
        return dev


    ##############################
    # Persistent XML change APIs #
    ##############################

    # Device Add/Remove
    def add_device(self, devobj):
        """
        Redefine guest with appended device XML 'devxml'
        """
        def change(guest):
            guest.add_device(devobj)
        ret = self._redefine(change)
        self.redefine_cached()
        return ret

    def remove_device(self, devobj):
        """
        Remove passed device from the inactive guest XML
        """
        # HACK: If serial and console are both present, they both need
        # to be removed at the same time
        con = None
        if hasattr(devobj, "virtmanager_console_dup"):
            con = getattr(devobj, "virtmanager_console_dup")

        def change(guest):
            def rmdev(editdev):
                if con:
                    rmcon = _find_device(guest, con)
                    if rmcon:
                        guest.remove_device(rmcon)

                guest.remove_device(editdev)
            return self._redefine_device(rmdev, devobj, False)

        ret = self._redefine(change)
        self.redefine_cached()
        return ret

    def define_cpu(self, vcpus=_SENTINEL, maxvcpus=_SENTINEL,
        cpuset=_SENTINEL, model=_SENTINEL, sockets=_SENTINEL,
        cores=_SENTINEL, threads=_SENTINEL):
        def change(guest):
            if vcpus != _SENTINEL:
                guest.curvcpus = int(vcpus)
            if maxvcpus != _SENTINEL:
                guest.vcpus = int(maxvcpus)
            if cpuset != _SENTINEL:
                guest.cpuset = cpuset

            if sockets != _SENTINEL:
                guest.cpu.sockets = sockets
                guest.cpu.cores = cores
                guest.cpu.threads = threads

            if model != _SENTINEL:
                if model in guest.cpu.SPECIAL_MODES:
                    guest.cpu.set_special_mode(model)
                else:
                    guest.cpu.model = model
        return self._redefine(change)

    def define_memory(self, memory=_SENTINEL, maxmem=_SENTINEL):
        def change(guest):
            if memory != _SENTINEL:
                guest.memory = int(memory)
            if maxmem != _SENTINEL:
                guest.maxmemory = int(maxmem)
        return self._redefine(change)

    def define_name(self, newname):
        return self._define_name_helper("domain",
                                        self.conn.rename_vm,
                                        newname)

    def define_overview(self, machine=_SENTINEL, description=_SENTINEL,
        title=_SENTINEL, idmap_list=_SENTINEL):
        def change(guest):
            if machine != _SENTINEL:
                guest.os.machine = machine
            if description != _SENTINEL:
                guest.description = description or None
            if title != _SENTINEL:
                guest.title = title or None

            if idmap_list != _SENTINEL:
                if idmap_list is not None:
                    # pylint: disable=unpacking-non-sequence
                    (uid_target, uid_count, gid_target, gid_count) = idmap_list
                    guest.idmap.uid_start = 0
                    guest.idmap.uid_target = uid_target
                    guest.idmap.uid_count = uid_count
                    guest.idmap.gid_start = 0
                    guest.idmap.gid_target = gid_target
                    guest.idmap.gid_count = gid_count
                else:
                    guest.idmap.clear()

        return self._redefine(change)

    def define_boot(self, boot_order=_SENTINEL, boot_menu=_SENTINEL,
        kernel=_SENTINEL, initrd=_SENTINEL, dtb=_SENTINEL,
        kernel_args=_SENTINEL, init=_SENTINEL):

        def _change_boot_order(guest):
            boot_dev_order = []
            devmap = dict((dev.vmmidstr, dev) for dev in
                          self.get_bootable_devices())
            for b in boot_order:
                if b in devmap:
                    boot_dev_order.append(devmap[b])

            # Unset the traditional boot order
            guest.os.bootorder = []

            # Unset device boot order
            for dev in guest.get_all_devices():
                dev.boot.order = None

            count = 1
            for origdev in boot_dev_order:
                dev = self._lookup_device_to_define(origdev, guest=guest)
                if not dev:
                    continue
                dev.boot.order = count
                count += 1

        def change(guest):
            if boot_order != _SENTINEL:
                if self.can_use_device_boot_order():
                    _change_boot_order(guest)
                else:
                    guest.os.bootorder = boot_order

            if boot_menu != _SENTINEL:
                guest.os.enable_bootmenu = bool(boot_menu)
            if init != _SENTINEL:
                guest.os.init = init

            if kernel != _SENTINEL:
                guest.os.kernel = kernel or None
            if initrd != _SENTINEL:
                guest.os.initrd = initrd or None
            if dtb != _SENTINEL:
                guest.os.dtb = dtb or None
            if kernel_args != _SENTINEL:
                guest.os.kernel_args = kernel_args or None
        return self._redefine(change)

    def define_disk(self, devobj, use_live_device,
        path=_SENTINEL, readonly=_SENTINEL, serial=_SENTINEL,
        shareable=_SENTINEL, removable=_SENTINEL, cache=_SENTINEL,
        io=_SENTINEL, driver_type=_SENTINEL, bus=_SENTINEL, addrstr=_SENTINEL,
        iotune_rbs=_SENTINEL, iotune_ris=_SENTINEL, iotune_tbs=_SENTINEL,
        iotune_tis=_SENTINEL, iotune_wbs=_SENTINEL, iotune_wis=_SENTINEL):
        def _change_bus(editdev):
            oldprefix = editdev.get_target_prefix()[0]
            oldbus = editdev.bus
            editdev.bus = bus

            if oldbus == bus:
                return

            editdev.address.clear()
            editdev.address.set_addrstr(addrstr)

            if oldprefix == editdev.get_target_prefix()[0]:
                return

            used = []
            disks = (self.get_disk_devices() +
                     self.get_disk_devices(inactive=True))
            for d in disks:
                used.append(d.target)

            if editdev.target:
                used.remove(editdev.target)

            editdev.target = None
            editdev.generate_target(used)

        def change(editdev):
            if path != _SENTINEL:
                editdev.path = path
                if not use_live_device:
                    editdev.sync_path_props()

            if readonly != _SENTINEL:
                editdev.read_only = readonly
            if shareable != _SENTINEL:
                editdev.shareable = shareable
            if removable != _SENTINEL:
                editdev.removable = removable

            if cache != _SENTINEL:
                editdev.driver_cache = cache or None
            if io != _SENTINEL:
                editdev.driver_io = io or None
            if driver_type != _SENTINEL:
                editdev.driver_type = driver_type or None
            if serial != _SENTINEL:
                editdev.serial = serial or None

            if iotune_rbs != _SENTINEL:
                editdev.iotune_rbs = iotune_rbs
            if iotune_ris != _SENTINEL:
                editdev.iotune_ris = iotune_ris
            if iotune_tbs != _SENTINEL:
                editdev.iotune_tbs = iotune_tbs
            if iotune_tis != _SENTINEL:
                editdev.iotune_tis = iotune_tis
            if iotune_wbs != _SENTINEL:
                editdev.iotune_wbs = iotune_wbs
            if iotune_wis != _SENTINEL:
                editdev.iotune_wis = iotune_wis

            if bus != _SENTINEL:
                _change_bus(editdev)

        return self._redefine_device(change, devobj, use_live_device)

    def define_network(self, devobj, use_live_device,
        ntype=_SENTINEL, source=_SENTINEL,
        mode=_SENTINEL, model=_SENTINEL, addrstr=_SENTINEL,
        vtype=_SENTINEL, managerid=_SENTINEL, typeid=_SENTINEL,
        typeidversion=_SENTINEL, instanceid=_SENTINEL):

        def change(editdev):
            if ntype != _SENTINEL:
                editdev.source = None

                editdev.type = ntype
                editdev.source = source
                editdev.source_mode = mode or None

            if model != _SENTINEL:
                if editdev.model != model:
                    editdev.address.clear()
                    editdev.address.set_addrstr(addrstr)
                editdev.model = model

            if vtype != _SENTINEL:
                editdev.virtualport.type = vtype or None
                editdev.virtualport.managerid = managerid or None
                editdev.virtualport.typeid = typeid or None
                editdev.virtualport.typeidversion = typeidversion or None
                editdev.virtualport.instanceid = instanceid or None
        return self._redefine_device(change, devobj, use_live_device)

    def define_graphics(self, devobj, use_live_device,
        listen=_SENTINEL, port=_SENTINEL, tlsport=_SENTINEL,
        passwd=_SENTINEL, keymap=_SENTINEL, gtype=_SENTINEL):
        def change(editdev):
            if listen != _SENTINEL:
                editdev.listen = listen
            if port != _SENTINEL:
                editdev.port = port
            if tlsport != _SENTINEL:
                editdev.tlsPort = tlsport
            if passwd != _SENTINEL:
                editdev.passwd = passwd
            if keymap != _SENTINEL:
                editdev.keymap = keymap
            if gtype != _SENTINEL:
                editdev.type = gtype
        return self._redefine_device(change, devobj, use_live_device)

    def define_sound(self, devobj, use_live_device, model=_SENTINEL):
        def change(editdev):
            if model != _SENTINEL:
                if editdev.model != model:
                    editdev.address.clear()
                editdev.model = model
        return self._redefine_device(change, devobj, use_live_device)

    def define_video(self, devobj, use_live_device, model=_SENTINEL):
        def change(editdev):
            if model == _SENTINEL or model == editdev.model:
                return

            editdev.model = model
            editdev.address.clear()

            # Clear out heads/ram values so they reset to default. If
            # we ever allow editing these values in the UI we should
            # drop this
            editdev.vram = None
            editdev.heads = None
            editdev.ram = None

        return self._redefine_device(change, devobj, use_live_device)

    def define_watchdog(self, devobj, use_live_device,
        model=_SENTINEL, action=_SENTINEL):
        def change(editdev):
            if model != _SENTINEL:
                if editdev.model != model:
                    editdev.address.clear()
                editdev.model = model

            if action != _SENTINEL:
                editdev.action = action
        return self._redefine_device(change, devobj, use_live_device)

    def define_smartcard(self, devobj, use_live_device, model=_SENTINEL):
        def change(editdev):
            if model != _SENTINEL:
                editdev.mode = model
                editdev.type = editdev.TYPE_DEFAULT
        return self._redefine_device(change, devobj, use_live_device)

    def define_controller(self, devobj, use_live_device, model=_SENTINEL):
        def _change_model(editdev):
            if editdev.type == "usb":
                guest = self._get_xmlobj_to_define()
                ctrls = guest.get_devices("controller")
                ctrls = [x for x in ctrls if (x.type ==
                         VirtualController.TYPE_USB)]
                for dev in ctrls:
                    guest.remove_device(dev)

                if model == "ich9-ehci1":
                    for dev in VirtualController.get_usb2_controllers(
                            guest.conn):
                        guest.add_device(dev)
                else:
                    dev = VirtualController(guest.conn)
                    dev.type = "usb"
                    if model != "default":
                        dev.model = model
                    guest.add_device(dev)

            elif editdev.type == "scsi":
                if model == "default":
                    editdev.model = None
                else:
                    editdev.model = model
                self.hotplug(device=editdev)

        def change(editdev):
            if model != _SENTINEL:
                _change_model(editdev)

        return self._redefine_device(change, devobj, use_live_device)

    def define_filesystem(self, devobj, use_live_device, newdev=_SENTINEL):
        def change(editdev):
            if newdev == _SENTINEL:
                return

            # pylint: disable=maybe-no-member
            editdev.type = newdev.type
            editdev.mode = newdev.mode
            editdev.wrpolicy = newdev.wrpolicy
            editdev.driver = newdev.driver
            editdev.format = newdev.format
            editdev.readonly = newdev.readonly
            editdev.units = newdev.units
            editdev.source = newdev.source
            editdev.target = newdev.target

        return self._redefine_device(change, devobj, use_live_device)


    def define_hostdev(self, devobj, use_live_device, rom_bar=_SENTINEL):
        def change(editdev):
            if rom_bar != _SENTINEL:
                editdev.rom_bar = rom_bar
        return self._redefine_device(change, devobj, use_live_device)


    ####################
    # Hotplug routines #
    ####################

    def attach_device(self, devobj):
        """
        Hotplug device to running guest
        """
        if not self.is_active():
            return

        devxml = devobj.get_xml_config()
        self._backend.attachDevice(devxml)

    def detach_device(self, devobj):
        """
        Hotunplug device from running guest
        """
        if not self.is_active():
            return

        xml = devobj.get_xml_config()
        self._backend.detachDevice(xml)

    def _update_device(self, devobj, flags=None):
        if flags is None:
            flags = getattr(libvirt, "VIR_DOMAIN_DEVICE_MODIFY_LIVE", 1)

        xml = devobj.get_xml_config()
        logging.debug("Calling update_device with xml=\n%s", xml)
        self._backend.updateDeviceFlags(xml, flags)

    def hotplug(self, vcpus=_SENTINEL, memory=_SENTINEL, maxmem=_SENTINEL,
        description=_SENTINEL, title=_SENTINEL, storage_path=_SENTINEL,
        device=_SENTINEL):
        if not self.is_active():
            return

        def _hotplug_memory(val):
            if val != self.get_memory():
                self._backend.setMemory(val)
        def _hotplug_maxmem(val):
            if val != self.maximum_memory():
                self._backend.setMaxMemory(val)

        def _hotplug_metadata(val, mtype):
            if not self.conn.check_support(
                self.conn.SUPPORT_DOMAIN_SET_METADATA, self._backend):
                return
            flags = (libvirt.VIR_DOMAIN_AFFECT_LIVE |
                     libvirt.VIR_DOMAIN_AFFECT_CONFIG)
            self._backend.setMetadata(mtype, val, None, None, flags)

        if vcpus != _SENTINEL:
            vcpus = int(vcpus)
            if vcpus != self.vcpu_count():
                self._backend.setVcpus(vcpus)

        if memory != _SENTINEL:
            logging.info("Hotplugging curmem=%s maxmem=%s for VM '%s'",
                         memory, maxmem, self.get_name())

            actual_cur = self.get_memory()
            if memory:
                if maxmem < actual_cur:
                    # Set current first to avoid error
                    _hotplug_memory(memory)
                    _hotplug_maxmem(maxmem)
                else:
                    _hotplug_maxmem(maxmem)
                    _hotplug_memory(memory)
            else:
                _hotplug_maxmem(maxmem)

        if description != _SENTINEL:
            _hotplug_metadata(description,
                libvirt.VIR_DOMAIN_METADATA_DESCRIPTION)
        if title != _SENTINEL:
            _hotplug_metadata(title, libvirt.VIR_DOMAIN_METADATA_TITLE)

        if storage_path != _SENTINEL:
            # qemu originally only supported attach_device for updating
            # a device's path. Stick with that. We may need to differentiate
            # for other drivers that don't maintain back compat though
            self.attach_device(device)

        elif device != _SENTINEL:
            self._update_device(device)


    ########################
    # Libvirt API wrappers #
    ########################

    def _define(self, newxml):
        self.conn.define_domain(newxml)
    def _XMLDesc(self, flags):
        return self._backend.XMLDesc(flags)

    def get_autostart(self):
        return self._backend.autostart()
    def set_autostart(self, val):
        if self.get_autostart() == val:
            return
        self._backend.setAutostart(val)

    def job_info(self):
        return self._backend.jobInfo()
    def abort_job(self):
        self._backend.abortJob()

    def open_console(self, devname, stream, flags=0):
        return self._backend.openConsole(devname, stream, flags)

    def refresh_snapshots(self):
        self._snapshot_list = None

    def list_snapshots(self):
        if self._snapshot_list is None:
            newlist = []
            for rawsnap in self._backend.listAllSnapshots():
                newlist.append(vmmDomainSnapshot(self.conn, rawsnap))
            self._snapshot_list = newlist
        return self._snapshot_list[:]

    def revert_to_snapshot(self, snap):
        self._backend.revertToSnapshot(snap.get_backend())
        self.idle_add(self.force_update_status)

    def create_snapshot(self, xml, redefine=False):
        flags = 0
        if redefine:
            flags = (flags | libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_REDEFINE)

        if not redefine:
            logging.debug("Creating snapshot flags=%s xml=\n%s", flags, xml)
        self._backend.snapshotCreateXML(xml, flags)


    ########################
    # XML Parsing routines #
    ########################

    def is_container(self):
        return self.get_xmlobj().os.is_container()
    def is_xenpv(self):
        return self.get_xmlobj().os.is_xenpv()
    def is_hvm(self):
        return self.get_xmlobj().os.is_hvm()

    def get_uuid(self):
        return self.uuid
    def get_abi_type(self):
        return self.get_xmlobj().os.os_type
    def get_hv_type(self):
        return self.get_xmlobj().type
    def get_pretty_hv_type(self):
        return self.conn.pretty_hv(self.get_abi_type(), self.get_hv_type())
    def get_arch(self):
        return self.get_xmlobj().os.arch
    def get_init(self):
        return self.get_xmlobj().os.init
    def get_emulator(self):
        return self.get_xmlobj().emulator
    def get_machtype(self):
        return self.get_xmlobj().os.machine
    def get_idmap(self):
        return self.get_xmlobj().idmap

    def get_name_or_title(self):
        title = self.get_title()
        if title:
            return title
        return self.get_name()

    def get_title(self):
        return self.get_xmlobj(inactive=True).title

    def get_description(self):
        # Always show the inactive <description>, let's us fake hotplug
        # for a field that's strictly metadata
        return self.get_xmlobj(inactive=True).description

    def get_memory(self):
        return int(self.get_xmlobj().memory)
    def maximum_memory(self):
        return int(self.get_xmlobj().maxmemory)

    def vcpu_count(self):
        return int(self.get_xmlobj().curvcpus or self.get_xmlobj().vcpus)
    def vcpu_max_count(self):
        return int(self.get_xmlobj().vcpus)

    def vcpu_pinning(self):
        return self.get_xmlobj().cpuset or ""
    def get_cpu_config(self):
        return self.get_xmlobj().cpu

    def _convert_old_boot_order(self):
        boot_order = self._get_old_boot_order()
        ret = []
        disks = self.get_disk_devices()
        nets = self.get_network_devices()

        for b in boot_order:
            if b == "network":
                ret += [n.vmmidstr for n in nets]
            if b == "hd":
                ret += [d.vmmidstr for d in disks if
                        d.device not in ["cdrom", "floppy"]]
            if b == "cdrom":
                ret += [d.vmmidstr for d in disks if d.device == "cdrom"]
            if b == "floppy":
                ret += [d.vmmidstr for d in disks if d.device == "floppy"]
        return ret

    def _get_device_boot_order(self):
        devs = self.get_bootable_devices()
        order = []
        for dev in devs:
            if not dev.boot.order:
                continue
            order.append((dev.vmmidstr, dev.boot.order))

        if not order:
            # No devices individually marked bootable, convert traditional
            # boot XML to fine grained, for the UI.
            return self._convert_old_boot_order()

        order.sort(key=lambda p: p[1])
        return [p[0] for p in order]

    def _get_old_boot_order(self):
        return self.get_xmlobj().os.bootorder
    def get_boot_order(self):
        if self.can_use_device_boot_order():
            return self._get_device_boot_order()
        return self._get_old_boot_order()
    def get_boot_menu(self):
        guest = self.get_xmlobj()
        return bool(guest.os.enable_bootmenu)
    def get_boot_kernel_info(self):
        guest = self.get_xmlobj()
        return (guest.os.kernel, guest.os.initrd,
                guest.os.dtb, guest.os.kernel_args)

    # XML Device listing

    def get_serial_devs(self):
        devs = self.get_char_devices()
        devlist = []

        devlist += [x for x in devs if x.virtual_device_type == "serial"]
        devlist += [x for x in devs if x.virtual_device_type == "console"]
        return devlist

    def _build_device_list(self, device_type,
                           refresh_if_nec=True, inactive=False):
        guest = self.get_xmlobj(refresh_if_nec=refresh_if_nec,
                                inactive=inactive)
        devs = guest.get_devices(device_type)

        for idx in range(len(devs)):
            devs[idx].vmmindex = idx
            devs[idx].vmmidstr = devs[idx].virtual_device_type + ("%.3d" % idx)

        return devs

    def get_network_devices(self, refresh_if_nec=True):
        return self._build_device_list("interface", refresh_if_nec)
    def get_video_devices(self):
        return self._build_device_list("video")
    def get_hostdev_devices(self):
        return self._build_device_list("hostdev")
    def get_watchdog_devices(self):
        return self._build_device_list("watchdog")
    def get_input_devices(self):
        return self._build_device_list("input")
    def get_graphics_devices(self):
        return self._build_device_list("graphics")
    def get_sound_devices(self):
        return self._build_device_list("sound")
    def get_controller_devices(self):
        return self._build_device_list("controller")
    def get_filesystem_devices(self):
        return self._build_device_list("filesystem")
    def get_smartcard_devices(self):
        return self._build_device_list("smartcard")
    def get_redirdev_devices(self):
        return self._build_device_list("redirdev")
    def get_tpm_devices(self):
        return self._build_device_list("tpm")
    def get_rng_devices(self):
        return self._build_device_list("rng")
    def get_panic_devices(self):
        return self._build_device_list("panic")

    def get_disk_devices(self, refresh_if_nec=True, inactive=False):
        devs = self._build_device_list("disk", refresh_if_nec, inactive)

        # Iterate through all disks and calculate what number they are
        # HACK: We are making a variable in VirtualDisk to store the index
        idx_mapping = {}
        for dev in devs:
            devtype = dev.device
            bus = dev.bus
            key = devtype + (bus or "")

            if key not in idx_mapping:
                idx_mapping[key] = 1

            dev.disk_bus_index = idx_mapping[key]
            idx_mapping[key] += 1

        return devs

    def get_char_devices(self):
        devs = []
        serials     = self._build_device_list("serial")
        parallels   = self._build_device_list("parallel")
        consoles    = self._build_device_list("console")
        channels    = self._build_device_list("channel")

        for devicelist in [serials, parallels, consoles, channels]:
            devs.extend(devicelist)

        # Don't display <console> if it's just a duplicate of <serial>
        if (len(consoles) > 0 and len(serials) > 0):
            con = consoles[0]
            ser = serials[0]

            if (con.type == ser.type and
                con.target_type is None or con.target_type == "serial"):
                ser.virtmanager_console_dup = con
                devs.remove(con)

        return devs

    def can_use_device_boot_order(self):
        # Return 'True' if guest can use new style boot device ordering
        return self.conn.check_support(
            self.conn.SUPPORT_CONN_DEVICE_BOOTORDER)

    def get_bootable_devices(self):
        devs = self.get_disk_devices()
        devs += self.get_network_devices()
        devs += self.get_hostdev_devices()

        # redirdev can also be marked bootable, but it should be rarely
        # used and clutters the UI
        return devs


    ############################
    # Domain lifecycle methods #
    ############################

    # All these methods are usually run asynchronously from threads, so
    # let's be extra careful and have anything which might touch UI
    # or GObject.props invoked in an idle callback

    def _unregister_reboot_listener(self):
        if self.reboot_listener is None:
            return

        try:
            self.idle_add(self.disconnect, self.reboot_listener)
            self.reboot_listener = None
        except:
            pass

    def manual_reboot(self):
        """
        Attempt a manual reboot by invoking 'shutdown', then listen
        for a state change and restart the VM
        """
        def reboot_listener(vm, ignore1, ignore2, self):
            if vm.is_crashed():
                # Abandon reboot plans
                self.reboot_listener = None
                return True

            if not vm.is_shutoff():
                # Not shutoff, continue waiting
                return

            try:
                logging.debug("Fake reboot detected shutdown. Restarting VM")
                vm.startup()
            except:
                logging.exception("Fake reboot startup failed")

            self.reboot_listener = None
            return True

        self._unregister_reboot_listener()

        # Request a shutdown
        self.shutdown()

        def add_reboot():
            self.reboot_listener = self.connect_opt_out("status-changed",
                                                    reboot_listener, self)
        self.idle_add(add_reboot)

    def shutdown(self):
        self._install_abort = True
        self._unregister_reboot_listener()
        self._backend.shutdown()
        self.idle_add(self.force_update_status)

    def reboot(self):
        self._install_abort = True
        self._backend.reboot(0)
        self.idle_add(self.force_update_status)

    def destroy(self):
        self._install_abort = True
        self._unregister_reboot_listener()
        self._backend.destroy()
        self.idle_add(self.force_update_status)

    def reset(self):
        self._install_abort = True
        self._backend.reset(0)
        self.idle_add(self.force_update_status)

    def startup(self):
        if self.get_cloning():
            raise RuntimeError(_("Cannot start guest while cloning "
                                 "operation in progress"))

        pre_startup_ret = []
        self.emit("pre-startup", pre_startup_ret)

        for error in pre_startup_ret:
            raise RuntimeError(error)

        self._backend.create()
        self.idle_add(self.force_update_status)

    def suspend(self):
        self._backend.suspend()
        self.idle_add(self.force_update_status)

    def delete(self, force=True):
        flags = 0
        if force:
            flags |= getattr(libvirt,
                             "VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA", 0)
            flags |= getattr(libvirt, "VIR_DOMAIN_UNDEFINE_MANAGED_SAVE", 0)
        try:
            self._backend.undefineFlags(flags)
        except libvirt.libvirtError:
            logging.exception("libvirt undefineFlags failed, "
                              "falling back to old style")
            self._backend.undefine()

    def resume(self):
        if self.get_cloning():
            raise RuntimeError(_("Cannot resume guest while cloning "
                                 "operation in progress"))

        self._backend.resume()
        self.idle_add(self.force_update_status)

    def hasSavedImage(self):
        if not self.managedsave_supported:
            return False
        try:
            return self._backend.hasManagedSaveImage(0)
        except libvirt.libvirtError, e:
            if not util.exception_is_libvirt_error(e, "VIR_ERR_NO_DOMAIN"):
                raise
            return False

    def removeSavedImage(self):
        if not self.hasSavedImage():
            return
        self._backend.managedSaveRemove(0)

    def save(self, filename=None, meter=None):
        self._install_abort = True

        if meter:
            start_job_progress_thread(self, meter, _("Saving domain to disk"))

        if not self.managedsave_supported:
            self._backend.save(filename)
        else:
            self._backend.managedSave(0)

        self.idle_add(self.force_update_status)


    def support_downtime(self):
        return self.conn.check_support(
            self.conn.SUPPORT_DOMAIN_MIGRATE_DOWNTIME, self._backend)

    def migrate_set_max_downtime(self, max_downtime, flag=0):
        self._backend.migrateSetMaxDowntime(max_downtime, flag)

    def migrate(self, destconn, interface=None, rate=0,
                live=False, secure=False, unsafe=False, meter=None):
        self._install_abort = True

        newname = None

        flags = 0
        if live:
            flags |= libvirt.VIR_MIGRATE_LIVE

        if secure:
            flags |= libvirt.VIR_MIGRATE_PEER2PEER
            flags |= libvirt.VIR_MIGRATE_TUNNELLED

        if unsafe:
            flags |= libvirt.VIR_MIGRATE_UNSAFE

        destconn = destconn.get_backend().get_conn_for_api_arg()
        logging.debug("Migrating: conn=%s flags=%s dname=%s uri=%s rate=%s",
                      destconn, flags, newname, interface, rate)

        if meter:
            start_job_progress_thread(self, meter, _("Migrating domain"))

        self._backend.migrate(destconn, flags, newname, interface, rate)

        def define_cb():
            newxml = self.get_xml(inactive=True)
            destconn.define_domain(newxml)
        self.idle_add(define_cb)
        # Don't schedule any conn update, migrate dialog handles it for us


    #################
    # Stats helpers #
    #################

    def _sample_cpu_stats(self, info, now):
        if not self._enable_cpu_stats:
            return 0, 0, 0, 0

        prevCpuTime = 0
        prevTimestamp = 0
        cpuTime = 0
        cpuTimeAbs = 0
        pcentHostCpu = 0
        pcentGuestCpu = 0

        if len(self.record) > 0:
            prevTimestamp = self.record[0]["timestamp"]
            prevCpuTime = self.record[0]["cpuTimeAbs"]

        if not (info[0] in [libvirt.VIR_DOMAIN_SHUTOFF,
                            libvirt.VIR_DOMAIN_CRASHED]):
            guestcpus = info[3]
            cpuTime = info[4] - prevCpuTime
            cpuTimeAbs = info[4]
            hostcpus = self.conn.host_active_processor_count()

            pcentbase = (((cpuTime) * 100.0) /
                         ((now - prevTimestamp) * 1000.0 * 1000.0 * 1000.0))
            pcentHostCpu = pcentbase / hostcpus
            pcentGuestCpu = pcentbase / guestcpus

        pcentHostCpu = max(0.0, min(100.0, pcentHostCpu))
        pcentGuestCpu = max(0.0, min(100.0, pcentGuestCpu))

        return cpuTime, cpuTimeAbs, pcentHostCpu, pcentGuestCpu

    def _get_cur_rate(self, what):
        if len(self.record) > 1:
            ret = (float(self.record[0][what] -
                         self.record[1][what]) /
                   float(self.record[0]["timestamp"] -
                         self.record[1]["timestamp"]))
        else:
            ret = 0.0
        return max(ret, 0, 0)  # avoid negative values at poweroff

    def _set_max_rate(self, record, what):
        if record[what] > self.maxRecord[what]:
            self.maxRecord[what] = record[what]
    def _get_max_rate(self, name1, name2):
        return float(max(self.maxRecord[name1], self.maxRecord[name2]))

    def _get_record_helper(self, record_name):
        if len(self.record) == 0:
            return 0
        return self.record[0][record_name]

    def _vector_helper(self, record_name):
        vector = []
        stats = self.record
        for i in range(self.config.get_stats_history_length() + 1):
            if i < len(stats):
                vector.append(stats[i][record_name] / 100.0)
            else:
                vector.append(0)
        return vector

    def _in_out_vector_helper(self, name1, name2, ceil):
        vector = []
        stats = self.record
        if ceil is None:
            ceil = self._get_max_rate(name1, name2)
        maxlen = self.config.get_stats_history_length()

        for n in [name1, name2]:
            for i in range(maxlen + 1):
                if i < len(stats):
                    vector.append(float(stats[i][n]) / ceil)
                else:
                    vector.append(0.0)
        return vector

    def in_out_vector_limit(self, data, limit):
        l = len(data) / 2
        end = min(l, limit)
        if l > limit:
            data = data[0:end] + data[l:l + end]

        return [(x + y) / 2 for x, y in zip(data[0:end], data[end:end * 2])]

    def toggle_sample_network_traffic(self, ignore=None):
        self._enable_net_poll = self.config.get_stats_enable_net_poll()

        if self._enable_net_poll and len(self.record) > 1:
            rxBytes, txBytes = self._sample_network_traffic()
            self.record[0]["netRxKB"] = rxBytes / 1024
            self.record[0]["netTxKB"] = txBytes / 1024

    def toggle_sample_disk_io(self, ignore=None):
        self._enable_disk_poll = self.config.get_stats_enable_disk_poll()

        if self._enable_disk_poll and len(self.record) > 1:
            rdBytes, wrBytes = self._sample_disk_io()
            self.record[0]["diskRdKB"] = rdBytes / 1024
            self.record[0]["diskWrKB"] = wrBytes / 1024

    def toggle_sample_mem_stats(self, ignore=None):
        self._enable_mem_stats = self.config.get_stats_enable_memory_poll()

    def toggle_sample_cpu_stats(self, ignore=None):
        self._enable_cpu_stats = self.config.get_stats_enable_cpu_poll()


    ###################
    # Stats accessors #
    ###################

    def stats_memory(self):
        return self._get_record_helper("curmem")
    def cpu_time(self):
        return self._get_record_helper("cpuTime")
    def host_cpu_time_percentage(self):
        return self._get_record_helper("cpuHostPercent")
    def guest_cpu_time_percentage(self):
        return self._get_record_helper("cpuGuestPercent")
    def network_rx_rate(self):
        return self._get_record_helper("netRxRate")
    def network_tx_rate(self):
        return self._get_record_helper("netTxRate")
    def disk_read_rate(self):
        return self._get_record_helper("diskRdRate")
    def disk_write_rate(self):
        return self._get_record_helper("diskWrRate")

    def get_memory_pretty(self):
        return util.pretty_mem(self.get_memory())
    def maximum_memory_pretty(self):
        return util.pretty_mem(self.maximum_memory())

    def network_traffic_rate(self):
        return self.network_tx_rate() + self.network_rx_rate()
    def network_traffic_max_rate(self):
        return self._get_max_rate("netRxRate", "netTxRate")
    def disk_io_rate(self):
        return self.disk_read_rate() + self.disk_write_rate()
    def disk_io_max_rate(self):
        return self._get_max_rate("diskRdRate", "diskWrRate")

    def host_cpu_time_vector(self):
        return self._vector_helper("cpuHostPercent")
    def guest_cpu_time_vector(self):
        return self._vector_helper("cpuGuestPercent")
    def stats_memory_vector(self):
        return self._vector_helper("currMemPercent")
    def network_traffic_vector(self, ceil=None):
        return self._in_out_vector_helper("netRxRate", "netTxRate", ceil)
    def disk_io_vector(self, ceil=None):
        return self._in_out_vector_helper("diskRdRate", "diskWrRate", ceil)

    def host_cpu_time_vector_limit(self, limit):
        cpudata = self.host_cpu_time_vector()
        if len(cpudata) > limit:
            cpudata = cpudata[0:limit]
        return cpudata
    def guest_cpu_time_vector_limit(self, limit):
        cpudata = self.guest_cpu_time_vector()
        if len(cpudata) > limit:
            cpudata = cpudata[0:limit]
        return cpudata
    def memory_usage_vector_limit(self, limit):
        return self.in_out_vector_limit(self.stats_memory_vector(),
                                        limit)
    def network_traffic_vector_limit(self, limit, ceil=None):
        return self.in_out_vector_limit(self.network_traffic_vector(ceil),
                                        limit)
    def disk_io_vector_limit(self, limit, ceil=None):
        return self.in_out_vector_limit(self.disk_io_vector(ceil), limit)


    ###################
    # Status helpers ##
    ###################

    def _normalize_status(self, status):
        if status == libvirt.VIR_DOMAIN_NOSTATE:
            return libvirt.VIR_DOMAIN_RUNNING
        elif status == libvirt.VIR_DOMAIN_BLOCKED:
            return libvirt.VIR_DOMAIN_RUNNING
        return status

    def is_active(self):
        return not self.is_shutoff()
    def is_shutoff(self):
        return self.status() == libvirt.VIR_DOMAIN_SHUTOFF
    def is_crashed(self):
        return self.status() == libvirt.VIR_DOMAIN_CRASHED
    def is_stoppable(self):
        return self.status() in [libvirt.VIR_DOMAIN_RUNNING,
                                 libvirt.VIR_DOMAIN_PAUSED,
                                 libvirt.VIR_DOMAIN_PMSUSPENDED]
    def is_destroyable(self):
        return (self.is_stoppable() or
                self.status() in [libvirt.VIR_DOMAIN_CRASHED])
    def is_runable(self):
        return self.status() in [libvirt.VIR_DOMAIN_SHUTOFF,
                                 libvirt.VIR_DOMAIN_CRASHED]
    def is_pauseable(self):
        return self.status() in [libvirt.VIR_DOMAIN_RUNNING]
    def is_unpauseable(self):
        return self.status() in [libvirt.VIR_DOMAIN_PAUSED]
    def is_paused(self):
        return self.status() in [libvirt.VIR_DOMAIN_PAUSED]

    def run_status(self):
        return self.pretty_run_status(self.status(), self.hasSavedImage())

    def run_status_reason(self):
        return self.pretty_status_reason(self.status(), self.status_reason())

    def run_status_icon_name(self):
        status = self.status()
        if status not in vm_status_icons:
            logging.debug("Unknown status %d, using NOSTATE", status)
            status = libvirt.VIR_DOMAIN_NOSTATE
        return vm_status_icons[status]

    def force_update_status(self, from_event=False):
        """
        Fetch current domain state and clear status cache
        """
        if not from_event and self._using_events():
            return

        try:
            info = self._backend.info()
            self._update_status(info[0])
        except libvirt.libvirtError:
            # Transient domain might have disappeared, tell the connection
            # to update the domain list
            logging.debug("force_update_status: Triggering domain "
                "list refresh")
            self.conn.schedule_priority_tick(pollvm=True, force=True)

    def _update_status(self, status):
        """
        Internal helper to change cached status to 'status' and signal
        clients if we actually changed state
        """
        status = self._normalize_status(status)

        if status == self.lastStatus:
            return

        oldstatus = self.lastStatus
        self.lastStatus = status
        if self.domain_state_supported:
            self._lastStatusReason = self._backend.state()[1]

        # Send 'config-changed' before a status-update, so users
        # are operating with fresh XML
        self.refresh_xml()

        self.idle_emit("status-changed", oldstatus, status)

    def inspection_data_updated(self):
        self.idle_emit("inspection-changed")


    ##################
    # config helpers #
    ##################

    def on_console_scaling_changed(self, *args, **kwargs):
        return self.config.listen_pervm(self.uuid, "/scaling",
                                        *args, **kwargs)
    def set_console_scaling(self, value):
        self.config.set_pervm(self.uuid, "/scaling", value)
    def get_console_scaling(self):
        ret = self.config.get_pervm(self.uuid, "/scaling")
        if ret == -1:
            return self.config.get_console_scaling()
        return ret

    def on_console_resizeguest_changed(self, *args, **kwargs):
        return self.config.listen_pervm(self.uuid, "/resize-guest",
                                        *args, **kwargs)
    def set_console_resizeguest(self, value):
        self.config.set_pervm(self.uuid, "/resize-guest", value)
    def get_console_resizeguest(self):
        ret = self.config.get_pervm(self.uuid, "/resize-guest")
        if ret == -1:
            return self.config.get_console_resizeguest()
        return ret

    def set_details_window_size(self, w, h):
        self.config.set_pervm(self.uuid, "/vm-window-size", (w, h))
    def get_details_window_size(self):
        ret = self.config.get_pervm(self.uuid, "/vm-window-size")
        return ret

    def get_console_password(self):
        return self.config.get_pervm(self.uuid, "/console-password")
    def set_console_password(self, username, keyid):
        return self.config.set_pervm(self.uuid, "/console-password",
                                     (username, keyid))

    def get_cache_dir(self):
        ret = os.path.join(self.conn.get_cache_dir(), self.get_uuid())
        if not os.path.exists(ret):
            os.makedirs(ret, 0755)
        return ret


    ###################
    # Polling helpers #
    ###################

    def _sample_network_traffic(self):
        rx = 0
        tx = 0
        if (not self._stats_net_supported or
            not self._enable_net_poll or
            not self.is_active()):
            self._stats_net_skip = []
            return rx, tx

        for netdev in self.get_network_devices(refresh_if_nec=False):
            dev = netdev.target_dev
            if not dev:
                continue

            if dev in self._stats_net_skip:
                continue

            try:
                io = self._backend.interfaceStats(dev)
                if io:
                    rx += io[0]
                    tx += io[4]
            except libvirt.libvirtError, err:
                if util.is_error_nosupport(err):
                    logging.debug("Net stats not supported: %s", err)
                    self._stats_net_supported = False
                else:
                    logging.error("Error reading net stats for "
                                  "'%s' dev '%s': %s",
                                  self.get_name(), dev, err)
                    if self.is_active():
                        logging.debug("Adding %s to skip list", dev)
                        self._stats_net_skip.append(dev)
                    else:
                        logging.debug("Aren't running, don't add to skiplist")

        return rx, tx

    def _sample_disk_io(self):
        rd = 0
        wr = 0
        if (not self._stats_disk_supported or
            not self._enable_disk_poll or
            not self.is_active()):
            self._stats_disk_skip = []
            return rd, wr

        # Some drivers support this method for getting all usage at once
        if not self._summary_disk_stats_skip:
            try:
                io = self._backend.blockStats('')
                if io:
                    rd = io[1]
                    wr = io[3]
                    return rd, wr
            except libvirt.libvirtError:
                self._summary_disk_stats_skip = True

        # did not work, iterate over all disks
        for disk in self.get_disk_devices(refresh_if_nec=False):
            dev = disk.target
            if not dev:
                continue

            if dev in self._stats_disk_skip:
                continue

            try:
                io = self._backend.blockStats(dev)
                if io:
                    rd += io[1]
                    wr += io[3]
            except libvirt.libvirtError, err:
                if util.is_error_nosupport(err):
                    logging.debug("Disk stats not supported: %s", err)
                    self._stats_disk_supported = False
                else:
                    logging.error("Error reading disk stats for "
                                  "'%s' dev '%s': %s",
                                  self.get_name(), dev, err)
                    if self.is_active():
                        logging.debug("Adding %s to skip list", dev)
                        self._stats_disk_skip.append(dev)
                    else:
                        logging.debug("Aren't running, don't add to skiplist")

        return rd, wr

    def _sample_mem_stats(self):
        if (not self.mem_stats_supported or
            not self._enable_mem_stats or
            not self.is_active()):
            return 0, 0

        curmem = 0
        totalmem = 1
        try:
            stats = self._backend.memoryStats()
            # did we get both required stat items back?
            if set(['actual', 'rss']).issubset(
                    set(stats.keys())):
                curmem = stats['rss']
                totalmem = stats['actual']
        except libvirt.libvirtError, err:
            logging.error("Error reading mem stats: %s", err)

        pcentCurrMem = curmem * 100.0 / totalmem
        pcentCurrMem = max(0.0, min(pcentCurrMem, 100.0))

        return pcentCurrMem, curmem


    def tick(self, stats_update=True):
        if not self._using_events():
            self._invalidate_xml()

        info = []
        if not self._using_events() or self._enable_cpu_stats:
            info = self._backend.info()

        if stats_update:
            self._tick_stats(info)

        if not self._using_events():
            self._update_status(info[0])

        if stats_update:
            self.idle_emit("resources-sampled")

    def _tick_stats(self, info):
        expected = self.config.get_stats_history_length()
        current = len(self.record)
        if current > expected:
            del self.record[expected:current]

        # Xen reports complete crap for Dom0 max memory
        # (ie MAX_LONG) so lets clamp it to the actual
        # physical RAM in machine which is the effective
        # real world limit
        if self.is_management_domain() and info:
            info[1] = self.conn.host_memory_size()

        now = time.time()
        (cpuTime, cpuTimeAbs,
         pcentHostCpu, pcentGuestCpu) = self._sample_cpu_stats(info, now)
        pcentCurrMem, curmem = self._sample_mem_stats()
        rdBytes, wrBytes = self._sample_disk_io()
        rxBytes, txBytes = self._sample_network_traffic()

        newStats = {
            "timestamp": now,
            "cpuTime": cpuTime,
            "cpuTimeAbs": cpuTimeAbs,
            "cpuHostPercent": pcentHostCpu,
            "cpuGuestPercent": pcentGuestCpu,
            "curmem": curmem,
            "currMemPercent": pcentCurrMem,
            "diskRdKB": rdBytes / 1024,
            "diskWrKB": wrBytes / 1024,
            "netRxKB": rxBytes / 1024,
            "netTxKB": txBytes / 1024,
        }

        for r in ["diskRd", "diskWr", "netRx", "netTx"]:
            newStats[r + "Rate"] = self._get_cur_rate(r + "KB")
            self._set_max_rate(newStats, r + "Rate")

        self.record.insert(0, newStats)


########################
# Libvirt domain class #
########################

class vmmDomainVirtinst(vmmDomain):
    """
    Domain object backed by a virtinst Guest object.

    Used for launching a details window for customizing a VM before install.
    """
    def __init__(self, conn, backend, key):
        vmmDomain.__init__(self, conn, backend, key)

        self._orig_xml = ""

    def get_name(self):
        return self._backend.name
    def get_id(self):
        return -1
    def hasSavedImage(self):
        return False

    def _XMLDesc(self, flags):
        raise RuntimeError("Shouldn't be called")

    def get_xml(self, *args, **kwargs):
        ignore = args
        ignore = kwargs
        return self._backend.get_install_xml(install=False)

    def _refresh_orig_xml(self):
        # We need to cache origxml in order to have something to diff against
        if not self._orig_xml:
            self._orig_xml = self._backend.get_xml_config()

    def get_xmlobj(self, inactive=False, refresh_if_nec=True):
        self._refresh_orig_xml()
        return self._backend
    def _reparse_xml(self, *args, **kwargs):
        ignore = args
        ignore = kwargs

    def _define(self, newxml):
        ignore = newxml
        self._orig_xml = ""
        self.emit("config-changed")

    def _redefine_xml(self, newxml):
        return self._redefine_helper(self._orig_xml, newxml)

    def refresh_xml(self, forcesignal=False):
        # No caching, so no refresh needed
        return

    def snapshots_supported(self):
        return False

    def get_autostart(self):
        return self._backend.autostart
    def set_autostart(self, val):
        self._backend.autostart = bool(val)
        self.emit("config-changed")

    def define_name(self, newname):
        def change(guest):
            guest.name = str(newname)
        return self._redefine(change)
