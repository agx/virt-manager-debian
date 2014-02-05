#
# Copyright (C) 2007, 2013 Red Hat, Inc.
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

from virtManager.baseclass import vmmGObject


class vmmNetDevice(vmmGObject):
    """
    Backend indepent class for a host network device.
    Filled in by a combination of interface and nodedev APIs
    """
    def __init__(self, name, mac, is_shared, bridge=None):
        vmmGObject.__init__(self)

        self.name = name
        self.mac = mac
        self.shared = is_shared
        self.bridge = bridge

    def _cleanup(self):
        pass

    def get_name(self):
        return self.name

    def is_shared(self):
        return self.shared

    def get_bridge(self):
        return self.bridge

    def get_mac(self):
        return self.mac
