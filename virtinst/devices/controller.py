#
# Copyright 2010, 2013, 2014 Red Hat, Inc.
# Cole Robinson <crobinso@redhat.com>
#
# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

from .device import Device
from ..xmlbuilder import XMLProperty


class DeviceController(Device):
    XML_NAME = "controller"

    TYPE_IDE             = "ide"
    TYPE_FDC             = "fdc"
    TYPE_SCSI            = "scsi"
    TYPE_SATA            = "sata"
    TYPE_VIRTIOSERIAL    = "virtio-serial"
    TYPE_USB             = "usb"
    TYPE_PCI             = "pci"
    TYPE_CCID            = "ccid"

    @staticmethod
    def get_recommended_types(_guest):
        return [DeviceController.TYPE_SCSI,
                DeviceController.TYPE_USB,
                DeviceController.TYPE_VIRTIOSERIAL,
                DeviceController.TYPE_CCID]

    @staticmethod
    def pretty_type(ctype):
        pretty_mappings = {
            DeviceController.TYPE_IDE:             "IDE",
            DeviceController.TYPE_FDC:              _("Floppy"),
            DeviceController.TYPE_SCSI:            "SCSI",
            DeviceController.TYPE_SATA:            "SATA",
            DeviceController.TYPE_VIRTIOSERIAL:    "VirtIO Serial",
            DeviceController.TYPE_USB:             "USB",
            DeviceController.TYPE_PCI:             "PCI",
            DeviceController.TYPE_CCID:            "CCID",
       }

        if ctype not in pretty_mappings:
            return ctype
        return pretty_mappings[ctype]

    @staticmethod
    def get_usb2_controllers(conn):
        ret = []
        ctrl = DeviceController(conn)
        ctrl.type = "usb"
        ctrl.model = "ich9-ehci1"
        ret.append(ctrl)

        ctrl = DeviceController(conn)
        ctrl.type = "usb"
        ctrl.model = "ich9-uhci1"
        ctrl.master_startport = 0
        ret.append(ctrl)

        ctrl = DeviceController(conn)
        ctrl.type = "usb"
        ctrl.model = "ich9-uhci2"
        ctrl.master_startport = 2
        ret.append(ctrl)

        ctrl = DeviceController(conn)
        ctrl.type = "usb"
        ctrl.model = "ich9-uhci3"
        ctrl.master_startport = 4
        ret.append(ctrl)
        return ret

    @staticmethod
    def get_usb3_controller(conn, guest):
        ignore = guest
        ctrl = DeviceController(conn)
        ctrl.type = "usb"
        ctrl.model = "nec-xhci"
        if conn.check_support(conn.SUPPORT_CONN_QEMU_XHCI):
            ctrl.model = "qemu-xhci"
        if conn.check_support(conn.SUPPORT_CONN_USB3_PORTS):
            # 15 is the max ports qemu supports, might as well
            # Add as many as possible
            ctrl.ports = 15
        return ctrl


    _XML_PROP_ORDER = ["type", "index", "model", "master_startport"]

    type = XMLProperty("./@type")
    model = XMLProperty("./@model")
    vectors = XMLProperty("./@vectors", is_int=True)
    ports = XMLProperty("./@ports", is_int=True)
    master_startport = XMLProperty("./master/@startport", is_int=True)

    index = XMLProperty("./@index", is_int=True)

    def pretty_desc(self):
        ret = self.pretty_type(self.type)
        if self.type == "scsi":
            if self.model == "virtio-scsi":
                ret = "Virtio " + ret
            elif self.address.type == "spapr-vio":
                ret = "sPAPR " + ret
        if self.type == "pci" and self.model == "pcie-root":
            ret = "PCIe"
        return ret


    ##################
    # Default config #
    ##################

    def set_defaults(self, _guest):
        if self.index is None:
            self.index = 0
