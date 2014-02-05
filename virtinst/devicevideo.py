#
# Copyright 2009, 2013 Red Hat, Inc.
# Cole Robinson <crobinso@redhat.com>
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

from virtinst import VirtualDevice
from virtinst.xmlbuilder import XMLProperty


class VirtualVideoDevice(VirtualDevice):

    virtual_device_type = VirtualDevice.VIRTUAL_DEV_VIDEO

    # Default models list
    MODEL_DEFAULT = "default"
    MODELS = ["cirrus", "vga", "vmvga", "xen", "qxl", MODEL_DEFAULT]

    @staticmethod
    def pretty_model(model):
        if model in ["qxl", "vmvga", "vga"]:
            return model.upper()
        return model.capitalize()


    _XML_PROP_ORDER = ["model", "vram", "heads"]
    model = XMLProperty("./model/@type",
                        default_cb=lambda s: "cirrus",
                        default_name=MODEL_DEFAULT)
    vram = XMLProperty("./model/@vram", is_int=True)
    ram = XMLProperty("./model/@ram", is_int=True)
    heads = XMLProperty("./model/@heads", is_int=True)


VirtualVideoDevice.register_type()
