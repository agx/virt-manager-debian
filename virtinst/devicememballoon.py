# Copyright (C) 2013 Red Hat, Inc.
#
# Copyright 2012
# Eiichi Tsukata <devel@etsukata.com>
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


class VirtualMemballoon(VirtualDevice):
    virtual_device_type = VirtualDevice.VIRTUAL_DEV_MEMBALLOON

    MODEL_DEFAULT = "virtio"
    MODELS = ["xen", "none", MODEL_DEFAULT]

    model = XMLProperty("./@model", default_cb=lambda s: s.MODEL_DEFAULT)


VirtualMemballoon.register_type()
