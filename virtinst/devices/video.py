#
# Copyright 2009, 2013 Red Hat, Inc.
#
# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

from .device import Device
from ..xmlbuilder import XMLProperty


class DeviceVideo(Device):
    XML_NAME = "video"

    _XML_PROP_ORDER = ["model", "vram", "heads", "vgamem"]
    model = XMLProperty("./model/@type")
    vram = XMLProperty("./model/@vram", is_int=True)
    vram64 = XMLProperty("./model/@vram64", is_int=True)
    ram = XMLProperty("./model/@ram", is_int=True)
    heads = XMLProperty("./model/@heads", is_int=True)
    vgamem = XMLProperty("./model/@vgamem", is_int=True)
    accel3d = XMLProperty("./model/acceleration/@accel3d", is_yesno=True)


    ##################
    # Default config #
    ##################

    @staticmethod
    def default_model(guest):
        if guest.os.is_pseries():
            return "vga"
        if guest.os.is_arm_machvirt() or guest.os.is_riscv_virt():
            return "virtio"
        if guest.conn.is_qemu() and guest.os.is_s390x():
            return "virtio"
        if guest.has_spice() and guest.os.is_x86():
            if guest.has_gl():
                return "virtio"
            return "qxl"
        if guest.os.is_hvm():
            if guest.conn.is_qemu():
                return "qxl"
            return "vga"
        return None

    def set_defaults(self, guest):
        if not self.model:
            self.model = self.default_model(guest)
        if self.model == 'virtio' and guest.has_gl():
            self.accel3d = True
