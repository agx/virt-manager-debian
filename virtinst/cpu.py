#
# Copyright 2010, 2013 Red Hat, Inc.
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

from virtinst.xmlbuilder import XMLBuilder, XMLProperty, XMLChildProperty


class CPUFeature(XMLBuilder):
    """
    Class for generating <cpu> child <feature> XML
    """

    POLICIES = ["force", "require", "optional", "disable", "forbid"]

    _XML_ROOT_NAME = "feature"
    _XML_PROP_ORDER = ["policy", "name"]

    name = XMLProperty("./@name")
    policy = XMLProperty("./@policy")


class CPU(XMLBuilder):
    """
    Class for generating <cpu> XML
    """
    MATCHS = ["minimum", "exact", "strict"]

    _XML_ROOT_NAME = "cpu"
    _XML_PROP_ORDER = ["mode", "match", "model", "vendor",
                       "sockets", "cores", "threads", "features"]

    special_mode_was_set = False
    # These values are exposed on the command line, so are stable API
    SPECIAL_MODE_HOST_MODEL_ONLY = "host-model-only"
    SPECIAL_MODE_HV_DEFAULT = "hv-default"
    SPECIAL_MODE_HOST_COPY = "host-copy"
    SPECIAL_MODE_HOST_MODEL = "host-model"
    SPECIAL_MODE_HOST_PASSTHROUGH = "host-passthrough"
    SPECIAL_MODE_CLEAR = "clear"
    SPECIAL_MODES = [SPECIAL_MODE_HOST_MODEL_ONLY, SPECIAL_MODE_HV_DEFAULT,
                     SPECIAL_MODE_HOST_COPY, SPECIAL_MODE_HOST_MODEL,
                     SPECIAL_MODE_HOST_PASSTHROUGH, SPECIAL_MODE_CLEAR]
    def set_special_mode(self, val):
        if (val == self.SPECIAL_MODE_HOST_MODEL or
            val == self.SPECIAL_MODE_HOST_PASSTHROUGH):
            self.model = None
            self.mode = val
        elif val == self.SPECIAL_MODE_HOST_COPY:
            self.copy_host_cpu()
        elif (val == self.SPECIAL_MODE_HV_DEFAULT or
              val == self.SPECIAL_MODE_CLEAR):
            self.clear()
        elif val == self.SPECIAL_MODE_HOST_MODEL_ONLY:
            if self.conn.caps.host.cpu.model:
                self.model = self.conn.caps.host.cpu.model
        else:
            raise RuntimeError("programming error: unknown "
                "special cpu mode '%s'" % val)

        self.special_mode_was_set = True

    def add_feature(self, name, policy="require"):
        feature = CPUFeature(self.conn)
        feature.name = name
        feature.policy = policy

        self._add_child(feature)
    def remove_feature(self, feature):
        self._remove_child(feature)
    features = XMLChildProperty(CPUFeature)

    def copy_host_cpu(self):
        """
        Enact the equivalent of qemu -cpu host, pulling all info
        from capabilities about the host CPU
        """
        cpu = self.conn.caps.host.cpu
        if not cpu.model:
            raise ValueError(_("No host CPU reported in capabilities"))

        self.mode = "custom"
        self.match = "exact"
        self.model = cpu.model
        self.vendor = cpu.vendor

        for feature in self.features:
            self.remove_feature(feature)
        for name in cpu.features.names():
            self.add_feature(name)

    def vcpus_from_topology(self):
        """
        Determine the CPU count represented by topology, or 1 if
        no topology is set
        """
        self.set_topology_defaults()
        if self.sockets:
            return self.sockets * self.cores * self.threads
        return 1

    def set_topology_defaults(self, vcpus=None):
        """
        Fill in unset topology values, using the passed vcpus count if
        required
        """
        if (self.sockets is None and
            self.cores is None and
            self.threads is None):
            return

        if vcpus is None:
            if self.sockets is None:
                self.sockets = 1
            if self.threads is None:
                self.threads = 1
            if self.cores is None:
                self.cores = 1

        vcpus = int(vcpus or 0)
        if not self.sockets:
            if not self.cores:
                self.sockets = vcpus / self.threads
            else:
                self.sockets = vcpus / self.cores

        if not self.cores:
            if not self.threads:
                self.cores = vcpus / self.sockets
            else:
                self.cores = vcpus / (self.sockets * self.threads)

        if not self.threads:
            self.threads = vcpus / (self.sockets * self.cores)

        return


    ##################
    # XML properties #
    ##################

    def _set_model(self, val):
        if val:
            self.mode = "custom"
            if not self.match:
                self.match = "exact"
        return val
    model = XMLProperty("./model", set_converter=_set_model)

    match = XMLProperty("./@match")
    vendor = XMLProperty("./vendor")
    mode = XMLProperty("./@mode")

    sockets = XMLProperty("./topology/@sockets", is_int=True)
    cores = XMLProperty("./topology/@cores", is_int=True)
    threads = XMLProperty("./topology/@threads", is_int=True)
